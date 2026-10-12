"""Independent instrumented examples supporting check review, not model scores."""
from pathlib import Path
import argparse
from .pipeline import read,save,digest,identity,code_hash
from .compiler import run_checks

PROBES={
 "types":[
  ("默认整型",'printf("%d",_Generic(123,int:1,default:0));',"1"),
  ("浮点默认",'printf("%d",_Generic(3.14,double:1,default:0));',"1"),
  ("整数除法截断",'printf("%d",-7/2);',"-3"),
  ("浮点截断",'printf("%d",(int)3.999f);',"3"),
  ("1U 的类型",'printf("%d",_Generic(1U,unsigned int:1,default:0));',"1"),
  ("int 与 double 的共同类型",'printf("%d",_Generic(10/2.0,double:1,default:0));',"1"),
  ("接收类型不反向改变表达式",'double x=7/2; printf("%.1f",x);',"3.0"),
  ("显式转换的位置",'printf("%.1f %.1f",(double)5/2,(double)(5/2));',"2.5 2.0"),
  ("转换表达式不改原变量",'int n=10; double tmp=(double)n; printf("%d %d",_Generic(n,int:1,default:0),n);',"1 10"),
  ("模转换",'printf("%d",(unsigned int)-1==UINT_MAX);',"1"),
  ("可表示整数转换保持数值",'printf("%d",(short)100);',"100")],
 "if":[
  ("标量条件的真值语义",'int n=-5;if(n)printf("T");else printf("F");',"T"),
  ("空语句对控制范围的破坏",'int x=5,y=0;if(x>10);y=20;printf("%d",y);',"20"),
  ("一次执行不重新选分支",'int x=1,y=0;if(x){x=0;}else{y=1;}printf("%d",y);',"0"),
  ("分支体的语句范围",'int a=0,x=0,y=0;if(a)x=1;y=2;printf("%d",y);',"2"),
  ("未进入外层则不执行内层",'int a=0,b=1,x=0;if(a)if(b)x=1;else x=2;printf("%d",x);',"0"),
  ("选择链首命中后停止判断",'int b_calls=0;if(1){}else if(++b_calls){}printf("%d",b_calls);',"0"),
  ("独立 if 可以多次命中",'int a=1,b=1,x=0,y=0;if(a)x++;if(b)y++;printf("%d %d",x,y);',"1 1"),
  ("后续 if 读取新状态",'int x=1,y=0;if(x)x=0;if(x)y=1;printf("%d %d",x,y);',"0 0")],
 "for":[
  ("首判为假与零次执行",'int i;for(i=10;i>100;i++){i=-1;}printf("%d",i);',"10"),
  ("体后更新顺序",'int i=0;for(i=0;i<2;i++){i+=10;}printf("%d",i);',"11"),
  ("外部变量最终值",'int i;for(i=0;i<10;i++){}printf("%d",i);',"10"),
  ("continue 的执行逻辑",'int i=2,h=0;for(;i<3;i++){continue;h++;}printf("%d %d",i,h);',"3 0"),
  ("break 退出机制",'int i=2,h=0;for(;i<3;i++){break;h++;}printf("%d %d",i,h);',"2 0"),
  ("return 结束机制",'for(int i=0;i<3;i++,puts("update")){if(i==1)return;}puts("after");',"update\n"),
  ("正常退出时的条件判断次数",'int tests=0;for(int i=0;(tests++,i<5);i++){}printf("%d",tests);',"6"),
  ("循环体修改变量",'for(int i=0;i<5;i++){printf("%d ",i);i+=2;}',"0 3 "),
  ("无符号变量倒序终止失败",'unsigned int i=0;i--;printf("%d",i>=0);',"1"),
  ("switch 内 break 的作用域",'for(int i=0;i<2;i++){switch(i){case 0:break;default:break;}printf("A");}',"AA"),
  ("省略条件视为真",'int hits=0;for(;;){hits++;break;}printf("%d",hits);',"1"),
  ("for 的单语句体",'int i,x=0,y=0;for(i=0;i<2;i++)x++;y++;printf("%d",y);',"1"),
  ("for 的空语句体",'int i,x=0;for(i=0;i<3;i++);x++;printf("%d",x);',"1")]
}


def run(root,gcc):
    for topic,probes in PROBES.items():
        final=read(root/topic/"final.json")
        by_name={p["name"]:p for p in final["core"]["points"]}
        primary={c["point_id"]:c for c in final["primary_checks"]}
        checks=[]
        for name,code,expected in probes:
            pid=by_name[name]["id"]
            key="probe_"+pid
            checks.append({"id":identity(topic,"check",key),"key":key,"knowledge_ids":[pid],"kind":"runtime",
                "question":"独立仪表化核验："+name,"code":code,"sample_return_type":"void","predicted_stdout":expected,
                "explanation":"由Codex据题目或规则设计并审阅的核验，不冒充千问原生答案得分。",
                "platform_assumptions":[],"reviewed_question_hash":digest(primary[pid])})
        save(root/topic/"review-probes.json",checks)
        results=run_checks({"checks":checks},gcc,root/topic/"review-probe-code",[code_hash(c) for c in checks],read(root/"compiler-environment.json"))
        assert all(r['status']=='executed' and r['model_prediction_matches'] for r in results),results
        print(topic,len(results),"independent instrumented examples passed",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("root",type=Path);parser.add_argument("--gcc",required=True)
    args=parser.parse_args();run(args.root,args.gcc)
