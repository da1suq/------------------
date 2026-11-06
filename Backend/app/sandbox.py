import io
import json
import tarfile

import docker
from docker.errors import DockerException, ImageNotFound


# Новый язык = новая запись здесь
LANGUAGES = {
    "python": {
        "image": "python:3.12-alpine",
        "filename": "main.py",
        # только проверка синтаксиса, на диск ничего не пишет
        "compile": ["python3", "-c",
                    "compile(open('/sandbox/main.py').read(), 'main.py', 'exec')"],
        "run": ["python3", "/sandbox/main.py"],
    },
}

MAX_PROCESSES = 64                    # от fork-бомб
TMP_SIZE = "64m"
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
COMPILE_TIMEOUT = 10                  # сек


# Работает внутри контейнера: запускает решение на одном тесте
# Аргументы: <лимит_сек> <файл_входа> <команда запуска...>
RUNNER_CODE = r'''
import json, os, resource, signal, subprocess, sys, time

time_limit = float(sys.argv[1])
input_path = sys.argv[2]
command = sys.argv[3:]
max_output = int(os.environ.get("MAX_OUTPUT_BYTES", "10485760"))

result = {"status": "ok", "time": 0.0, "exit_code": 0, "memory_kb": 0,
          "stdout": "", "stderr": ""}

with open(input_path, "rb") as stdin_file, \
     open("/tmp/out.txt", "wb") as stdout_file, \
     open("/tmp/err.txt", "wb") as stderr_file:
    start = time.perf_counter()
    
    process = subprocess.Popen(command, stdin=stdin_file, stdout=stdout_file,
                               stderr=stderr_file, start_new_session=True)
    try:
        process.wait(timeout=time_limit)
    except subprocess.TimeoutExpired:
        result["status"] = "tle"
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
    result["time"] = round(time.perf_counter() - start, 3)

result["exit_code"] = process.returncode
result["memory_kb"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
if result["status"] == "ok" and process.returncode != 0:
    result["status"] = "re"

with open("/tmp/out.txt", "rb") as f:
    result["stdout"] = f.read(max_output).decode("utf-8", errors="replace")
with open("/tmp/err.txt", "rb") as f:
    result["stderr"] = f.read(2000).decode("utf-8", errors="replace")

print(json.dumps(result))
'''


def make_result(verdict, execution_time=0.0, memory_mb=0.0, tests_passed=0,
                failed_test=None, message=""):
    # единый формат ответа для бэкенда
    return {
        "verdict": verdict,
        "execution_time": execution_time,
        "memory_used_mb": memory_mb,
        "tests_passed": tests_passed,
        "failed_test": failed_test,
        "message": message,
    }


def make_tar(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for path, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def normalize_output(text):
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines)


def get_image(client, image_name):
    try:
        client.images.get(image_name)
    except ImageNotFound:
        client.images.pull(image_name)


def start_container(client, image, memory_limit):
    return client.containers.run(
        image,
        command=["sleep", "300"],     # на случай, если контейнер не удалится
        detach=True,
        network_mode="none",
        mem_limit=f"{memory_limit}m",
        memswap_limit=f"{memory_limit}m",
        nano_cpus=1_000_000_000,
        pids_limit=MAX_PROCESSES,
        user="nobody",
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        tmpfs={"/tmp": f"rw,size={TMP_SIZE},mode=1777"},
        environment={
            "MAX_OUTPUT_BYTES": str(MAX_OUTPUT_BYTES),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )


def run_one_test(container, lang, test_number, time_limit):
    hard_timeout = str(int(time_limit) + 5)
    command = ["timeout", "-s", "KILL", hard_timeout,
               "python3", "/sandbox/runner.py", str(time_limit),
               f"/sandbox/tests/{test_number}.in"] + lang["run"]
    exit_code, output = container.exec_run(command)
    try:
        return json.loads(output.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        # раннер убит вместе с решением — обычно лимит памяти/процессов
        return {"status": "crash", "time": 0.0, "memory_kb": 0,
                "exit_code": exit_code, "stdout": "", "stderr": ""}


def execute_code(code: str, language: str, time_limit: float,
                 memory_limit: int, test_cases: list) -> dict:
    if language not in LANGUAGES:
        return make_result("CE", message=f"Язык '{language}' не поддерживается")
    if not test_cases:
        return make_result("SE", message="У задачи нет тестов")

    lang = LANGUAGES[language]
    container = None

    try:
        client = docker.from_env()
        get_image(client, lang["image"])
        container = start_container(client, lang["image"], memory_limit)

        files = {
            f"sandbox/{lang['filename']}": code,
            "sandbox/runner.py": RUNNER_CODE,
        }
        for i, test in enumerate(test_cases, start=1):
            files[f"sandbox/tests/{i}.in"] = test["input"]
        container.put_archive("/", make_tar(files))

        if lang.get("compile"):
            compile_cmd = ["timeout", "-s", "KILL", str(COMPILE_TIMEOUT)] + lang["compile"]
            exit_code, output = container.exec_run(compile_cmd)
            if exit_code != 0:
                error_text = output.decode("utf-8", errors="replace")[-2000:]
                return make_result("CE", message=error_text)

        max_time = 0.0
        max_memory_mb = 0.0

        for i, test in enumerate(test_cases, start=1):
            run = run_one_test(container, lang, i, time_limit)
            max_time = max(max_time, run["time"])
            max_memory_mb = max(max_memory_mb, round(run["memory_kb"] / 1024, 1))
            passed = i - 1

            def fail(verdict, message):
                return make_result(verdict, max_time, max_memory_mb, passed, i, message)

            if run["status"] == "tle":
                return fail("TLE", f"Превышено время на тесте {i} (лимит {time_limit} с)")

            if run["status"] == "crash":
                return fail("RE", f"Решение аварийно завершилось на тесте {i}: "
                                  f"превышен лимит памяти ({memory_limit} МБ) "
                                  f"или количества процессов")

            if run["status"] == "re":
                if run["exit_code"] == -9:   # убит системой — память
                    reason = f"превышен лимит памяти {memory_limit} МБ"
                else:
                    reason = run["stderr"].strip() or f"код выхода {run['exit_code']}"
                return fail("RE", f"Ошибка выполнения на тесте {i}: {reason}")

            if normalize_output(run["stdout"]) != normalize_output(test["output"]):
                return fail("WA", f"Неправильный ответ на тесте {i}")

        return make_result("OK", max_time, max_memory_mb, len(test_cases))

    except DockerException as error:
        return make_result("SE", message=f"Ошибка песочницы: {error}")

    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except DockerException:
                pass
