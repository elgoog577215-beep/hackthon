# Formal code runner

This service is the only supported path for grading formal code-submission
questions. The main FastAPI process must never execute hidden tests.

## Runtime contract

- Internal endpoints require `FORMAL_RUNNER_TOKEN`.
- Supported languages are Python and JavaScript.
- Hidden tests are registered before publication; the main application stores
  only `test_bundle_id`, its SHA-256 digest, and the test count.
- Every hidden test starts a new OCI container with networking disabled,
  a read-only root filesystem, non-root UID, all Linux capabilities removed,
  `no-new-privileges`, CPU/memory/process/time limits, and a 32 KB output cap.
- Results expose counts, failure categories, and resource usage only. Hidden
  input, expected output, and raw program output are never returned.

## Deployment

Use `docker-compose.runner.yml` on a Linux host after setting a long random
`FORMAL_RUNNER_TOKEN` and the Docker socket group ID in `DOCKER_GID`.
Pre-pull the configured Python and JavaScript images before serving traffic.
Keep port 8091 on the private service network.

The compose deployment requires a running Linux Docker engine. If the runner
health check is unavailable, implementation questions fail closed and are not
auto-published; output-prediction and state-trace questions remain available.

Mounting the Docker socket gives this small orchestration service control of
the local engine. Deploy it on a dedicated worker host, keep the API private,
and do not colocate unrelated production workloads on that engine.

## Windows 本地实验

仍使用 Linux OCI 容器执行代码，不在应用或 Windows Python 进程执行学生代码。
已配置的 WSL 发行版需具有可用 Docker 引擎并预拉取上述镜像。可在启动
Runner 前设置 `RUNNER_DOCKER_COMMAND` 为 JSON 参数数组，例如
`["wsl.exe", "-d", "YOUR_DISTRIBUTION", "--exec", "docker"]`。
该配置只由本地运行环境提供，判题请求不能指定执行命令。

从灵知应用目录运行 `python -m uvicorn runner.app:app --host 127.0.0.1 --port 8091`，
并在应用后端启动前注入匹配的 `FORMAL_RUNNER_URL` 与 `FORMAL_RUNNER_TOKEN`。
实际令牌与隐藏测试目录不进入仓库。健康检查验证 Docker 引擎可达；准备镜像后，
还需验证正误代码的实际执行。引擎或测试包不可用时保留提交并等待评阅，不能计为错误。
