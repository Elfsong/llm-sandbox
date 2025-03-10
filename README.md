## LLM Sandbox

*Securely Execute LLM-Generated Code with Ease*

![PyPI Downloads](https://static.pepy.tech/badge/llm-sandbox)

LLM Sandbox is a lightweight and portable sandbox environment designed to run large language model (LLM) generated code in a safe and isolated manner using Docker containers. This project aims to provide an easy-to-use interface for setting up, managing, and executing code in a controlled Docker environment, simplifying the process of running code generated by LLMs.

![](https://blog.duy.dev/content/images/size/w2000/2024/07/llm-sandbox--6--1.png)
### Features

- **Easy Setup:** Quickly create sandbox environments with minimal configuration.
- **Isolation:** Run your code in isolated Docker containers to prevent interference with your host system.
- **Flexibility:** Support for multiple programming languages.
- **Portability:** Use predefined Docker images or custom Dockerfiles.
- **Scalability:** Support Kubernetes and remote Docker host.

### Installation

#### Using Poetry

1. Ensure you have [Poetry](https://python-poetry.org/docs/#installation) installed.
2. Add the package to your project:

```sh
poetry add llm-sandbox
```

#### Using pip

1. Ensure you have [pip](https://pip.pypa.io/en/stable/installation/) installed.
2. Install the package:

```sh
pip install llm-sandbox
```

### Usage

#### Session Lifecycle

The `SandboxSession` class manages the lifecycle of the sandbox environment, including the creation and destruction of Docker containers. Here’s a typical lifecycle:

1. **Initialization:** Create a `SandboxSession` object with the desired configuration.
2. **Open Session:** Call the `open()` method to build/pull the Docker image and start the Docker container.
3. **Run Code:** Use the `run()` method to execute code inside the sandbox. Currently, it supports Python, Java, JavaScript, C++, Go, and Ruby. See [examples](examples) for more details.
4. **Close Session:** Call the `close()` method to stop and remove the Docker container. If the `keep_template` flag is set to `True`, the Docker image will not be removed, and the last container state will be committed to the image.

### Example

Here's a simple example to demonstrate how to use LLM Sandbox:

```python
from llm_sandbox import SandboxSession

# Create a new sandbox session
with SandboxSession(image="python:3.9.19-bullseye", keep_template=True, lang="python") as session:
    result = session.run("print('Hello, World!')")
    print(result)

# With custom Dockerfile
with SandboxSession(dockerfile="Dockerfile", keep_template=True, lang="python") as session:
    result = session.run("print('Hello, World!')")
    print(result)

# Or default image
with SandboxSession(lang="python", keep_template=True) as session:
    result = session.run("print('Hello, World!')")
    print(result)
```


LLM Sandbox also supports copying files between the host and the sandbox:

```python
from llm_sandbox import SandboxSession

with SandboxSession(lang="python", keep_template=True) as session:
    # Copy a file from the host to the sandbox
    session.copy_to_runtime("test.py", "/sandbox/test.py")

    # Run the copied Python code in the sandbox
    result = session.run("python /sandbox/test.py")
    print(result)

    # Copy a file from the sandbox to the host
    session.copy_from_runtime("/sandbox/output.txt", "output.txt")
```

For other languages usage, please refer to the [examples](examples/code_runner_docker.py).

You can also use [remote Docker host](https://docs.docker.com/config/daemon/remote-access/) as below:

```python
import docker
from llm_sandbox import SandboxSession

tls_config = docker.tls.TLSConfig(
    client_cert=("path/to/cert.pem", "path/to/key.pem"),
    ca_cert="path/to/ca.pem",
    verify=True
)
docker_client = docker.DockerClient(base_url="tcp://<your_host>:<port>", tls=tls_config)

with SandboxSession(
    client=docker_client,
    image="python:3.9.19-bullseye",
    keep_template=True,
    lang="python",
) as session:
    result = session.run("print('Hello, World!')")
    print(result)
```

For Kubernetes usage, please refer to the examples. Essentially, you just need to set the use_kubernetes flag to True and provide the Kubernetes client, or leave it as the default for the local context.

#### Integration
With Langchain integration, you can easily run the generated code in a safe and isolated environment. Here's an example of how to use LLM Sandbox with Langchain:

```python
from typing import Optional, List
from llm_sandbox import SandboxSession
from langchain import hub
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent


@tool
def run_code(lang: str, code: str, libraries: Optional[List] = None) -> str:
    """
    Run code in a sandboxed environment.
    :param lang: The language of the code.
    :param code: The code to run.
    :param libraries: The libraries to use, it is optional.
    :return: The output of the code.
    """
    with SandboxSession(lang=lang, verbose=False) as session:  # type: ignore[attr-defined]
        return session.run(code, libraries).text


if __name__ == "__main__":
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    prompt = hub.pull("hwchase17/openai-functions-agent")
    tools = [run_code]

    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    output = agent_executor.invoke(
        {
            "input": "Write python code to calculate Pi number by Monte Carlo method then run it."
        }
    )
    print(output)

    output = agent_executor.invoke(
        {
            "input": "Write python code to calculate the factorial of a number then run it."
        }
    )
    print(output)

    output = agent_executor.invoke(
        {"input": "Write python code to calculate the Fibonacci sequence then run it."}
    )
    print(output)
```

For Llama-Index:
```python
from typing import Optional, List
from llm_sandbox import SandboxSession

from llama_index.llms.openai import OpenAI
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import FunctionCallingAgentWorker


import nest_asyncio

nest_asyncio.apply()


def run_code(lang: str, code: str, libraries: Optional[List] = None) -> str:
    """
    Run code in a sandboxed environment.
    :param lang: The language of the code, must be one of ['python', 'java', 'javascript', 'cpp', 'go', 'ruby'].
    :param code: The code to run.
    :param libraries: The libraries to use, it is optional.
    :return: The output of the code.
    """
    with SandboxSession(lang=lang, verbose=False) as session:  # type: ignore[attr-defined]
        return session.run(code, libraries).text


if __name__ == "__main__":
    llm = OpenAI(model="gpt-4o", temperature=0)
    code_execution_tool = FunctionTool.from_defaults(fn=run_code)

    agent_worker = FunctionCallingAgentWorker.from_tools(
        [code_execution_tool],
        llm=llm,
        verbose=True,
        allow_parallel_tool_calls=False,
    )
    agent = agent_worker.as_agent()

    response = agent.chat(
        "Write python code to calculate Pi number by Monte Carlo method then run it."
    )
    print(response)

    response = agent.chat(
        "Write python code to calculate the factorial of a number then run it."
    )
    print(response)

    response = agent.chat(
        "Write python code to calculate the Fibonacci sequence then run it."
    )
    print(response)

    response = agent.chat("Calculate the sum of the first 10000 numbers.")
    print(response)
```

### Contributing

We welcome contributions to improve LLM Sandbox! Since I am a Python developer, I am not familiar with other languages. If you are interested in adding better support for other languages, please feel free to submit a pull request.

Here is a list of things you can do to contribute:
- [ ] Add Java maven support.
- [x] Add support for JavaScript.
- [x] Add support for C++.
- [x] Add support for Go.
- [ ] Add support for Ruby.
- [x] Add remote Docker host support.
- [x] Add remote Kubernetes cluster support.
- [x] Langchain integration.
- [x] LlamaIndex integration.
- [ ] Commit the last container state to the image before closing kubernetes session.

### License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
