import io
import os
import docker
import tarfile
import tempfile
from typing import List, Optional, Union

from docker.models.images import Image
from docker.models.containers import Container
from docker.types import Mount
from llm_sandbox.utils import (
    image_exists,
    get_libraries_installation_command,
    get_code_file_extension,
    get_code_execution_command,
)
from llm_sandbox.base import Session, ConsoleOutput
from llm_sandbox.const import (
    SupportedLanguage,
    SupportedLanguageValues,
    DefaultImage,
    NotSupportedLibraryInstallation,
)


class SandboxDockerSession(Session):
    def __init__(
        self,
        client: Optional[docker.DockerClient] = None,
        image: Optional[str] = None,
        dockerfile: Optional[str] = None,
        lang: str = SupportedLanguage.PYTHON,
        keep_template: bool = False,
        commit_container: bool = True,
        verbose: bool = False,
        mounts: Optional[list[Mount]] = None,
        container_configs: Optional[dict] = None,
    ):
        """
        Create a new sandbox session
        :param client: Docker client, if not provided, a new client will be created based on local Docker context
        :param image: Docker image to use
        :param dockerfile: Path to the Dockerfile, if image is not provided
        :param lang: Language of the code
        :param keep_template: if True, the image and container will not be removed after the session ends
        :param commit_container: if True, the Docker container will be commited after the session ends
        :param verbose: if True, print messages
        :param mounts: List of mounts to be mounted to the container
        :param container_configs: Additional configurations for the container, i.e. resources limits (cpu_count, mem_limit), etc.
        """
        super().__init__(lang, verbose)
        if image and dockerfile:
            raise ValueError("Only one of image or dockerfile should be provided")

        if lang not in SupportedLanguageValues:
            raise ValueError(
                f"Language {lang} is not supported. Must be one of {SupportedLanguageValues}"
            )

        if not image and not dockerfile:
            image = DefaultImage.__dict__[lang.upper()]

        self.lang: str = lang
        self.client: Optional[docker.DockerClient] = None

        if not client:
            if self.verbose:
                print("Using local Docker context since client is not provided..")

            self.client = docker.from_env()
        else:
            self.client = client

        self.image: Union[Image, str] = image
        self.dockerfile: Optional[str] = dockerfile
        self.container: Optional[Container] = None
        self.path = None
        self.keep_template = keep_template
        self.commit_container = commit_container
        self.is_create_template: bool = False
        self.verbose = verbose
        self.mounts = mounts
        self.container_configs = container_configs

    def open(self):
        warning_str = (
            "Since the `keep_template` flag is set to True the docker image will not be removed after the session ends "
            "and remains for future use."
        )
        if self.dockerfile:
            self.path = os.path.dirname(self.dockerfile)
            if self.verbose:
                f_str = f"Building docker image from {self.dockerfile}"
                f_str = f"{f_str}\n{warning_str}" if self.keep_template else f_str
                print(f_str)

            self.image, _ = self.client.images.build(
                path=self.path,
                dockerfile=os.path.basename(self.dockerfile),
                tag=f"sandbox-{self.lang.lower()}-{os.path.basename(self.path)}",
            )
            self.is_create_template = True

        if isinstance(self.image, str):
            if not image_exists(self.client, self.image):
                if self.verbose:
                    f_str = f"Pulling image {self.image}.."
                    f_str = f"{f_str}\n{warning_str}" if self.keep_template else f_str
                    print(f_str)

                self.image = self.client.images.pull(self.image)
                self.is_create_template = True
            else:
                self.image = self.client.images.get(self.image)
                if self.verbose:
                    print(f"Using image {self.image.tags[-1]}")

        self.container = self.client.containers.run(
            self.image,
            detach=True,
            tty=True,
            mounts=self.mounts,
            **self.container_configs if self.container_configs else {},
        )
        
        self.setup()

    def close(self):
        if self.container:
            if self.commit_container and isinstance(self.image, Image):
                self.container.commit(self.image.tags[-1])

            self.container.remove(force=True)
            self.container = None

        if self.is_create_template and not self.keep_template:
            # check if the image is used by any other container
            containers = self.client.containers.list(all=True)
            image_id = (
                self.image.id
                if isinstance(self.image, Image)
                else self.client.images.get(self.image).id
            )
            image_in_use = any(
                container.image.id == image_id for container in containers
            )

            if not image_in_use:
                if isinstance(self.image, str):
                    self.client.images.remove(self.image)
                elif isinstance(self.image, Image):
                    self.image.remove(force=True)
                else:
                    raise ValueError("Invalid image type")
            else:
                if self.verbose:
                    print(
                        f"Image {self.image.tags[-1]} is in use by other containers. Skipping removal.."
                    )

    def setup(self, libraries: Optional[List] = None):
        self.execute_command('apt update')
        self.execute_command('apt install time')

        if libraries:
            if self.lang.upper() in NotSupportedLibraryInstallation:
                raise ValueError(
                    f"Library installation has not been supported for {self.lang} yet!"
                )

            if self.lang == SupportedLanguage.GO:
                self.execute_command("mkdir -p /go_space")
                self.execute_command("go mod init go_space", workdir="/go_space")
                self.execute_command("go mod tidy", workdir="/go_space")

                for library in libraries:
                    command = get_libraries_installation_command(self.lang, library)
                    _ = self.execute_command(command, workdir="/go_space")
            else:
                for library in libraries:
                    command = get_libraries_installation_command(self.lang, library)
                    _ = self.execute_command(command)

    def run(self, code: str, run_memory_profile: bool, *args, **kwargs) -> ConsoleOutput:
        if not self.container:
            raise RuntimeError(
                "Session is not open. Please call open() method before running code."
            )

        with tempfile.TemporaryDirectory() as directory_name:
            code_file = os.path.join(directory_name, f"code.{get_code_file_extension(self.lang)}")
            profiler_file = "/home/nus_cisco_wp1/Projects/llm-sandbox/memory_profiler.sh"
            
            if self.lang == SupportedLanguage.GO:
                code_dest_file = "/go_space/code.go"
            else:
                code_dest_file = (
                    f"/tmp/code.{get_code_file_extension(self.lang)}"  # code_file
                )
            profiler_dest_path = "/tmp/memory_profiler.sh"

            with open(code_file, "w") as f:
                f.write(code)

            self.copy_to_runtime(code_file, code_dest_file)
            if run_memory_profile:
                self.copy_to_runtime(profiler_file, profiler_dest_path)

            output = ConsoleOutput()
            code_compiled= False
            commands = get_code_execution_command(self.lang, code_dest_file, run_memory_profile=run_memory_profile)
            
            for index, command in enumerate(commands):
                if self.lang == SupportedLanguage.GO:
                    output = self.execute_command(command, workdir="/go_space")
                else:
                    output = self.execute_command(command)
                    if self.verbose:
                        print(output.stdout)
                        print(output.stderr)
                        
            duration, peak_memory, integral, log = 0, 0, 0, list()
            if run_memory_profile:
                log_path = os.path.join(directory_name, 'mem_usage.log')
                if self.lang == SupportedLanguage.GO:
                    self.copy_from_runtime('/go_space/mem_usage.log', log_path)
                else:
                    self.copy_from_runtime('mem_usage.log', log_path)
                
                with open(log_path, "r") as mem_profile:
                    for line in mem_profile.readlines():
                        timestamp, mem = line.split(" ")
                        peak_memory = max(peak_memory, int(mem))
                        integral += peak_memory
                        log.append((int(timestamp), int(mem)))
                    duration = (log[-1][0] - log[0][0]) / 1000000
                os.remove(log_path)
                
                
            return {"stdout": output.stdout, "stderr": output.stderr, "peak_memory": peak_memory, "integral": integral, "duration": duration, 'log': log}

    def copy_from_runtime(self, src: str, dest: str):
        if not self.container:
            raise RuntimeError(
                "Session is not open. Please call open() method before copying files."
            )

        if self.verbose:
            print(f"Copying {self.container.short_id}:{src} to {dest}..")

        bits, stat = self.container.get_archive(src)
        if stat["size"] == 0:
            raise FileNotFoundError(f"File {src} not found in the container")

        tarstream = io.BytesIO(b"".join(bits))
        with tarfile.open(fileobj=tarstream, mode="r") as tar:
            tar.extractall(os.path.dirname(dest))

    def copy_to_runtime(self, src: str, dest: str):
        if not self.container:
            raise RuntimeError(
                "Session is not open. Please call open() method before copying files."
            )

        is_created_dir = False
        directory = os.path.dirname(dest)
        if directory and not self.container.exec_run(f"test -d {directory}")[0] == 0:
            self.container.exec_run(f"mkdir -p {directory}")
            is_created_dir = True

        if self.verbose:
            if is_created_dir:
                print(f"Creating directory {self.container.short_id}:{directory}")
            print(f"Copying {src} to {self.container.short_id}:{dest}..")

        tarstream = io.BytesIO()
        with tarfile.open(fileobj=tarstream, mode="w") as tar:
            tar.add(src, arcname=os.path.basename(src))

        tarstream.seek(0)
        self.container.put_archive(os.path.dirname(dest), tarstream)

    def execute_command(self, command: Optional[str], workdir: Optional[str] = None) -> ConsoleOutput:
        if not command:
            raise ValueError("Command cannot be empty")

        if not self.container:
            raise RuntimeError(
                "Session is not open. Please call open() method before executing commands."
            )

        if self.verbose:
            print(f"Executing command: {command}")

        if workdir:
            exit_code, exec_log = self.container.exec_run(command, stream=False, tty=False, workdir=workdir, demux=True)
        else:
            exit_code, exec_log = self.container.exec_run(command, stream=False, tty=False, demux=True)

        stdout = exec_log[0].decode("utf-8") if exec_log[0] else None
        stderr = exec_log[1].decode("utf-8") if exec_log[1] else None

        if self.verbose:
            print(f"stdout:\n{stdout}")
            print(f"stderr:\n{stderr}")

        return ConsoleOutput(stdout, stderr)
