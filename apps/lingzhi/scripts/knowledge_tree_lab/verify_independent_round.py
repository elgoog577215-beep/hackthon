"""Authored counterexamples and computations; no model code execution."""
from pathlib import Path
import argparse
from .pipeline import read,save,digest
from .independent_answers import literal_prefix


def verify(root):
    actual={}
    a=[1];b=a;actual['P1']={'check':a is b}
    d={'k':1};e=d;actual['P1']['transfer']=d is e
    a=[1];b=a;b.append(2);actual['P2']={'check':a}
    x=[10];y=x;x[0]=20;actual['P2']['transfer']=y
    a=[1];b=a;b=[9];actual['P3']={'check':a}
    m=[100];n=m;m=[200];actual['P3']['transfer']=n
    a=[[1]];b=a.copy();b.append([2]);actual['P4']={'check':a}
    c=[1,2];d=c.copy();d.append(3);actual['P4']['transfer']=c
    a=[[1]];b=a.copy();actual['P5']={'check':b[0] is a[0]}
    x=[{'v':1}];y=x.copy();actual['P5']['transfer']=y[0] is x[0]
    a=[[1]];b=a.copy();b[0].append(2);actual['P6']={'check':a}
    p=[[10,20]];q=p.copy();p[0].pop();actual['P6']['transfer']=q
    a=[[1]];b=a.copy();b[0]=[9];actual['P7']={'check':a}
    list_a=[[100]];list_b=list_a.copy();list_b[0]=[200];actual['P7']['transfer']=list_a
    receipts=[]
    for point in read(root/'candidates/python-final.json')['points']:
        for field in ('check','transfer'):
            parsed=literal_prefix(point[field]['answer']);value=actual[point['key']][field]
            receipts.append({'point_key':point['key'],'field':field,'question':point[field]['question'],
                'question_digest':digest(point[field]['question']),'actual':value,
                'model_answer':point[field]['answer'],'answer_correct':parsed is not None and parsed[1]==value})
    # An explicit countermodel: equal interaction forces, unequal masses, equal accelerations.
    # A has m=10, pair force=-20, other=+40; B has m=5, pair=+20, other=-10.
    physics={'mass_A':10,'mass_B':5,'pair_on_A':-20,'pair_on_B':20,'other_on_A':40,'other_on_B':-10}
    physics['acceleration_A']=(physics['pair_on_A']+physics['other_on_A'])/physics['mass_A']
    physics['acceleration_B']=(physics['pair_on_B']+physics['other_on_B'])/physics['mass_B']
    assert physics['acceleration_A']==physics['acceleration_B']==2
    physics['finding']='质量不等、相互作用力等大仍可有相同加速度；没有合外力条件不能直接断言谁更大。'
    # Rationalization identity at h=3 disproves the proposed intermediate expression.
    from fractions import Fraction
    h=3
    calculus={'piecewise_at_1':{'left_limit':2,'right_limit':4,'point_value':3,'two_sided_limit_exists':False},
        'sqrt_difference_quotient_h3':{'original':str(Fraction(2-1,h)),
             'correct_rationalized':str(Fraction(1,2+1)),
             'wrong_model_intermediate':str(Fraction(h,(1+h)+1)),
             'finding':'正确有理化为1/(sqrt(1+h)+1)，不是h/((1+h)+1)；最终1/2不能掩盖推导错误。'},
        'initial_piecewise_derivative_at_1':{'left':2,'right':2,'differentiable':True},
        'repaired_piecewise_at_1':{'value_at_1':1,'left_function_limit':1,'right_function_limit':3,
             'left_difference_quotient':'2+h','right_difference_quotient':'2/h+2',
             'right_quotients_at_h_0_1_0_01_0_001':[str(Fraction(2,h)+2) for h in (Fraction(1,10),Fraction(1,100),Fraction(1,1000))],
             'differentiable':False,'finding':'应保留f(1)=1；不能只分别对两段表达式求导就认为左右导数均为2。'}}
    assert calculus['sqrt_difference_quotient_h3']['original']==calculus['sqrt_difference_quotient_h3']['correct_rationalized']
    assert calculus['sqrt_difference_quotient_h3']['original']!=calculus['sqrt_difference_quotient_h3']['wrong_model_intermediate']
    save(root/'independent-computations.json',{'method':'Codex逐题读取后编写并执行的固定计算，不是任意题目自动求解器；未执行模型程序',
      'python':receipts,'physics_counterexample':physics,'calculus':calculus,
      'history_method':'逐条对照M1/M2/M3原文、证据范围及开放评分要求，不用关键词命中替代论证核验'})
    print('Python exact answers:',sum(r['answer_correct'] for r in receipts),'/',len(receipts))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);verify(p.parse_args().root)
