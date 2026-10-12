"""Independent, authored checks. Never executes text returned by the model."""
import argparse
from pathlib import Path
import sys
from .pipeline import save


def verify(root):
    checks=[]
    def check(key, actual, expected, purpose):
        checks.append({'key':key,'actual':actual,'expected':expected,'passed':actual==expected,'purpose':purpose})
    a=[1];b=a
    check('python.Q1',a is b,True,'冻结题答案')
    a=[1];b=a;b.append(2)
    check('python.Q2',a,[1,2],'冻结题答案')
    a=[1];b=a;b=[9]
    check('python.Q3',a,[1],'冻结题答案；独立重置')
    a=[[1]];b=a.copy();b.append([2])
    check('python.Q4',a,[[1]],'冻结题答案')
    a=[[1]];b=a.copy();b[0].append(2)
    check('python.Q5',a,[[1,2]],'冻结题答案')
    a=[[1]];b=a.copy();b[0]=[9]
    check('python.Q6',a,[[1]],'冻结题答案')
    a=[[3]];b=a.copy();b[0].append(4);b.append([5])
    check('python.R1',[a,b],[[[3,4]],[[3,4],[5]]],'冻结复测答案')
    a=[[3]];b=a.copy();b[0]=[8];b=[0]
    check('python.R2',a,[[3]],'冻结复测答案')
    a=[10];b=a.copy();c=b[0]
    check('python.N1.type',[type(c).__name__,type(a[0]).__name__],['int','int'],
          '检出新补题声称内层列表的错误；不执行模型代码，而是独立写出其已检查的三条普通列表操作')
    check('python.N1.is_list',isinstance(c,list),False,'模型答案“同一个列表对象：是”不成立')
    # Tiny explicitly authored erroneous models for the four Python hypotheses.
    a=[1];b=a.copy()
    check('python.A.wrong_model',a is b,False,'错规则赋值即复制的预测')
    a=[1];b=a;a=b=[9]
    check('python.B.wrong_model',a,[9],'错规则变量重绑同步传播的预测')
    a=[[1]];b=[item.copy() for item in a];b[0].append(2)
    check('python.C.wrong_model',a,[[1]],'错规则浅拷贝复制内层的预测')
    a=[[1]];b=a.copy();a[0]=b[0]=[9]
    check('python.D.wrong_model',a,[[9]],'错规则元素替换同步传播的预测')
    # Necessary is not sufficient: equal target alone cannot imply zero sum.
    check('physics.same_receiver_counterexample',3 + (-1),2,
          '抽象向量反例：同一受力对象上两个反向但不等大的力不平衡；非模型补题执行')
    check('physics.wrong_agent_mass_prediction',2>1,True,
          '本轮错规则按施力者质量比较，甲更重确实预测甲对乙更大')
    allowed=[(continuous,differentiable) for continuous in (False,True)
             for differentiable in (False,True) if not differentiable or continuous]
    check('calculus.contrapositive',all(c or not d for c,d in allowed),True,
          '从可导→连续允许的真值行验证不连续→不可导')
    check('calculus.inverse_counterexample',[(c,d) for c,d in allowed if not d and c],[(True,False)],
          '不可导→不连续存在反例，两个方向不能共用检查；具体例子为|x|在0')
    save(root/'independent-checks.json',{'runtime':sys.version.split()[0],
        'method':'固定、人工编写的局部运算及反例；未执行模型程序；不是通用语义求解器',
        'checks':checks,
        'manual_math':['Q1极限0、点值1，不连续；Q2差商h趋于0；Q3左右-1/+1；Q4正确蕴含，Q5/Q6反例成立。',
                       'R1平移不改变左右差商-1/+1；R2极限0不等于点值5，由不连续推出不可导。'],
        'manual_physics':['大小问题不检查方向或加速度；同受力对象仅是平衡必要条件；不同对象还须核对同一次相互作用。'],
        'manual_history':['A的两项原文陈述均可被观察到，但不等于所述事件均已核验。',
                          'B陈述收入增加和工时延长，不足推出生活质量改善或恶化；不能预先当作A的反例。',
                          '数量投票与立场偏好是不同错规则；未定义优先级及立场方向时不能唯一推出A真B假。']})
    assert all(c['passed'] for c in checks)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);verify(p.parse_args().root)
