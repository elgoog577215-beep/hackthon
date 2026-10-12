"""Restricted local C probe runner with explicit code-hash execution eligibility.

This is NOT a sandbox. Eligibility requires inspecting termination, defined C
behavior and absence of external side effects. Never expose to untrusted users.
"""
from pathlib import Path
import os
import re
import subprocess
from .pipeline import code_hash, digest, save

HEADERS = "#include <stdio.h>\n#include <limits.h>\n#include <float.h>\n#include <stdbool.h>\n"


def probe_environment(compiler, output):
    compiler = Path(compiler).resolve()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PATH": str(compiler.parent) + os.pathsep + os.environ.get("PATH", "")}
    source = output.with_suffix(".c")
    executable = output.with_suffix(".exe")
    source.write_text(HEADERS + r'''
int main(void) {
    printf("{\"CHAR_BIT\":%d,\"INT_MAX\":%d,\"UINT_MAX\":%u,"
           "\"SHRT_MAX\":%d,\"UCHAR_MAX\":%d,\"LONG_MAX\":%ld,"
           "\"LLONG_MAX\":%lld,\"FLT_RADIX\":%d,\"DBL_MANT_DIG\":%d}",
           CHAR_BIT, INT_MAX, UINT_MAX, SHRT_MAX, UCHAR_MAX, LONG_MAX,
           LLONG_MAX, FLT_RADIX, DBL_MANT_DIG);
    return 0;
}
''', encoding="utf-8")
    built = subprocess.run([str(compiler), "-std=c17", "-pedantic-errors", str(source), "-o", str(executable)],
                           env=env, capture_output=True, text=True, timeout=20)
    if built.returncode:
        raise RuntimeError("compiler_environment_probe_failed")
    observed = subprocess.run([str(executable)], env=env, capture_output=True, text=True, timeout=2, check=True)
    version = subprocess.run([str(compiler), "--version"], env=env, capture_output=True, text=True, timeout=2, check=True)
    import json
    result = json.loads(observed.stdout)
    result.update(compiler=version.stdout.splitlines()[0], language_mode="C17", only_this_environment_verified=True)
    save(output, result)
    return result


def restricted_code(code):
    # Reject preprocessor directives before stripping strings/comments.
    if re.search(r"^\s*#", code, re.M) or len(code) > 3000:
        return "directive_or_length"
    clean = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', "literal", code)
    clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", clean, flags=re.S)
    if any(s in clean for s in ("[", "]", "->", "#", "__")):
        return "outside_subset"
    if re.search(r"\b(?:asm|while|do|goto|typedef|struct|union|volatile)\b", clean):
        return "outside_subset"
    if re.search(r"(?<!&)&(?!&)", clean) or "%n" in code:
        return "address_or_write_format"
    calls = re.findall(r"\b([A-Za-z_]\w*)\s*\(", clean)
    if any(c not in {"if", "for", "switch", "printf", "puts", "sizeof", "_Generic"} for c in calls):
        return "unapproved_call"
    return None


def run_checks(doc, compiler, out, approvals, environment):
    compiler = Path(compiler).resolve()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PATH": str(compiler.parent) + os.pathsep + os.environ.get("PATH", "")}
    results = []
    for check in doc["checks"]:
        item = {"check_id": check["id"], "key": check["key"], "code_hash": code_hash(check),
                "environment_hash": digest(environment), "executed": False}
        if check["kind"] != "runtime":
            item["status"] = "static_review_required"
            results.append(item)
            continue
        blocked = restricted_code(check["code"])
        if blocked:
            item.update(status="subset_rejected", reason=blocked)
            results.append(item)
            continue
        if code_hash(check) not in approvals:
            item["status"] = "eligibility_review_required"
            results.append(item)
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", check["id"]):
            raise ValueError("unsafe_file_id")
        source = out / (check["id"] + ".c")
        source.write_text(HEADERS + "\n" + check["sample_return_type"] + " sample(void) {\n" +
                          check["code"] + "\n}\nint main(void){sample();return 0;}\n", encoding="utf-8")
        runs = []
        for optimization in ("-O0", "-O2"):
            executable = out / (check["id"] + optimization + ".exe")
            command = [str(compiler), "-std=c17", "-pedantic-errors", "-Wall", "-Wextra",
                       "-Werror=format", "-Werror=int-conversion", "-Werror=return-type",
                       optimization, str(source), "-o", str(executable)]
            try:
                built = subprocess.run(command, env=env, capture_output=True, text=True, errors="replace", timeout=20)
                run = {"optimization": optimization, "compile_returncode": built.returncode,
                       "compiler_output": built.stderr}
                if built.returncode:
                    run["status"] = "compile_failed"
                else:
                    executed = subprocess.run([str(executable)], env=env, capture_output=True, text=True,
                                              errors="replace", timeout=2)
                    run.update(status="executed", returncode=executed.returncode,
                               stdout=executed.stdout.replace("\r\n", "\n"), stderr=executed.stderr)
            except subprocess.TimeoutExpired:
                run = {"optimization": optimization, "status": "timeout"}
            runs.append(run)
        item["runs"] = runs
        if all(r.get("status") == "executed" and r["returncode"] == 0 for r in runs):
            agrees = runs[0]["stdout"] == runs[1]["stdout"]
            item.update(status="executed" if agrees else "optimization_disagrees", executed=True,
                        returncode=0, stdout=runs[0]["stdout"], optimization_agrees=agrees,
                        model_prediction_matches=runs[0]["stdout"] == check["predicted_stdout"])
        else:
            item["status"] = "compile_or_run_failed"
        results.append(item)
    save(out / "results.json", results)
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(probe_environment(args.gcc, args.output))
