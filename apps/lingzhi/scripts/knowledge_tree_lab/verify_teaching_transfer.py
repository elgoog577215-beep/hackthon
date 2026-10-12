"""Reviewed, finite transfer probes. Never execute model output or UB examples."""
from pathlib import Path
import argparse
from .compiler import probe_environment, run_checks
from .pipeline import code_hash, save

PROBES = [
    ("T1", 'printf("%d %d %d %d",_Generic(42,int:1,default:0),_Generic(1U,unsigned int:1,default:0),_Generic(6.25,double:1,default:0),_Generic(6.25f,float:1,default:0));', '1 1 1 1'),
    ("T2_common", 'printf("%d %d",_Generic(1+2.0,double:1,default:0),_Generic(1+1U,unsigned int:1,default:0));', '1 1'),
    ("T3", 'int a=9,b=4;double x=a/b,y=(double)a/b,z=(double)(a/b);printf("%.2f %.2f %.2f %d %d",x,y,z,_Generic(a,int:1,default:0),a);', '2.00 2.25 2.00 1 9'),
    ("T4_defined", 'printf("%d %d",(unsigned int)-2==UINT_MAX-1,(short)17);', '1 17'),
    ("T5_defined", 'printf("%d",(int)-4.75);', '-4'),
    ("I1_a", 'int x=-2,y=0;if(x){x=0;y=1;}else y=2;printf("%d %d",x,y);', '0 1'),
    ("I1_b", 'int x=-2,y=0;if(x);y=3;printf("%d %d",x,y);', '-2 3'),
    ("I2", 'for(int a=1;a>=0;a--){int b=0,x=5;if(a)if(b)x=1;else x=2;printf("%d ",x);}for(int a=1;a>=0;a--){int b=0,x=5;if(a){if(b)x=1;}else x=2;printf("%d ",x);}', '2 5 5 2 '),
    ("I3_a", 'int x=1,y=0;if(x==1)x=2;else if(x==2)y=7;printf("%d %d",x,y);', '2 0'),
    ("I3_b", 'int x=1,y=0;if(x==1)x=2;if(x==2)y=7;printf("%d %d",x,y);', '2 7'),
    ("F1", 'int init=0,test=0,iter=0;for(int i=(init++,2);(test++,i<5);(iter++,i++)){printf("%d ",i);}printf("|%d %d %d",init,test,iter);init=test=iter=0;for(int i=(init++,5);(test++,i<5);(iter++,i++)){}printf("|%d %d %d",init,test,iter);', '2 3 4 |1 4 3|1 1 0'),
    ("F2", 'int i=2;for(;i<5;){i+=2;}printf("%d",i);for(;;){break;}', '6'),
    ("F3", 'int i=0,c=0;for(;i<2;i++);c++;printf("%d %d|",i,c);i=0;c=0;for(;i<2;i++){c++;}printf("%d %d",i,c);', '2 1|2 2'),
    ("F4_continue", 'for(int i=0;i<4;(printf("U"),i++)){if(i==1)continue;printf("S");}printf("A");', 'SUUSUSUA'),
    ("F4_break", 'for(int i=0;i<4;(printf("U"),i++)){if(i==1)break;printf("S");}printf("A");', 'SUA'),
    ("F4_return", 'for(int i=0;i<4;(printf("U"),i++)){if(i==1)return;printf("S");}printf("A");', 'SU'),
    ("F5", 'for(int i=0;i<1;(printf("U"),i++)){switch(i){case 0:break;}printf("S");}printf("|");for(int i=0;i<1;(printf("U"),i++)){switch(i){case 0:continue;}printf("S");}', 'SU|U'),
    ("F6_defined", 'int j;for(j=0;j<5;j++){j++;}printf("%d",j);', '6'),
    ("F7_defined", 'unsigned int u=0;u--;printf("%d %d",u==UINT_MAX,u>=0);', '1 1'),
]


def verify(root, compiler):
    checks = [{"id": "transfer_" + key, "key": key, "kind": "runtime", "code": code,
               "sample_return_type": "void", "predicted_stdout": expected, "platform_assumptions": []} for key, code, expected in PROBES]
    save(root / "transfer-probes.json", checks)
    env = probe_environment(compiler, root / "transfer-environment.json")
    results = run_checks({"checks": checks}, compiler, root / "transfer-execution", {code_hash(c) for c in checks}, env)
    assert all(r["status"] == "executed" and r["model_prediction_matches"] for r in results), "transfer_probe_mismatch"
    save(root / "transfer-verification.json", {"programs": len(checks), "runs": len(checks)*2,
        "all_passed": True, "not_executed": ["T2假定的异平台整数提升", "T4实现定义转换", "T5浮点越界UB与任意整数精度", "F6作用域错误", "F7无退出循环和有符号溢出"],
        "limit": "实际执行只核验当前实现；不以运行结果证明可移植规范或真实学生诊断效度。"})
    print(len(checks), "reviewed programs passed at O0 and O2")


if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path);p.add_argument("--gcc",required=True);a=p.parse_args();verify(a.root,a.gcc)
