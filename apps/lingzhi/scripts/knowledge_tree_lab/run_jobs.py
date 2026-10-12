"""Execute frozen experiment jobs once, with the project's existing AIBase route."""
import argparse,asyncio,hashlib,json,logging,os,sys,time
from pathlib import Path
from .pipeline import read,save


async def main():
    parser=argparse.ArgumentParser();parser.add_argument("root",type=Path)
    parser.add_argument("--jobs",default="jobs.json");parser.add_argument("--job",default="all")
    args=parser.parse_args();root=args.root.resolve()
    app=Path(__file__).resolve().parents[2]
    if root.is_relative_to(app/"backend/data"):raise ValueError("isolated_root_required")
    manifest=read(root/"manifest.json")
    assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in manifest["input_hashes"].items())
    if args.jobs != "jobs.json":
        assert args.jobs == "repair-jobs.json" and manifest.get("repair_jobs_sha256") == hashlib.sha256((root/args.jobs).read_bytes()).hexdigest(), "repair_jobs_not_frozen"
    os.environ["LINGZHI_DATA_DIR"]=str(root/"isolated-data")
    os.environ["LINGZHI_GENERATION_TELEMETRY"]="false"
    logging.disable(logging.CRITICAL);sys.path.insert(0,str(app/"backend"))
    from ai_base import AIBase
    provider=AIBase()
    try:
        for job in read(root/args.jobs):
            if args.job not in ("all",job["id"]):continue
            folder=root/"calls"/job["id"];folder.mkdir(parents=True,exist_ok=True)
            result=folder/"result.json"
            if result.exists():raise ValueError("duplicate_job_refused:"+job["id"])
            if len(list((root/"calls").glob("*/result.json")))>=manifest["model_calls_max"]:raise ValueError("budget_exhausted")
            prompt=job["instruction"]+"\n输入："+json.dumps(job["input"],ensure_ascii=False)
            (folder/"prompt.txt").write_text(prompt,encoding="utf-8")
            save(result,{"state":"started","job":job["id"],"model":provider.model_smart})
            print("started",job["id"],flush=True)
            start=time.monotonic();telemetry=[];parts=[]
            task=asyncio.create_task(provider._call_llm(prompt,system_prompt="你是C17课程教学设计助手。只输出所需JSON，遵循给定知识与参数边界。不输出思考过程。所有内容仍是待验收候选。",
                retry_count=1,max_attempts=1,enable_thinking=False,max_tokens=job["max_tokens"],request_timeout_seconds=240,
                reject_truncated=True,require_stop=True,raise_on_failure=True,json_mode=False,on_content_delta=parts.append,telemetry_sink=telemetry.append))
            try:
                while not task.done():
                    await asyncio.wait({task},timeout=25)
                    (folder/"partial.txt").write_text("".join(parts),encoding="utf-8")
                    print("progress",job["id"],round(time.monotonic()-start,1),sum(map(len,parts)),flush=True)
                response=await task
                (folder/"raw.txt").write_text(response or "",encoding="utf-8")
                try:parsed=json.loads(response);mode="strict_json"
                except json.JSONDecodeError:parsed=provider._extract_json(response);mode="extracted_json"
                if not isinstance(parsed,dict):raise ValueError("invalid_json")
                save(folder/"parsed.json",parsed)
                save(result,{"state":"completed","job":job["id"],"model":provider.model_smart,"parse":mode,
                    "seconds":round(time.monotonic()-start,2),"telemetry":telemetry})
                print("completed",job["id"],flush=True)
            except Exception as exc:
                save(result,{"state":"failed","job":job["id"],"error_type":type(exc).__name__,"seconds":round(time.monotonic()-start,2),"telemetry":telemetry})
                print("failed",job["id"],type(exc).__name__,flush=True)
                break
    finally:
        if provider.client:await provider.client.close()


if __name__=="__main__":asyncio.run(main())
