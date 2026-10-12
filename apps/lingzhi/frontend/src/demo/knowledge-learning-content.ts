// Authored teaching examples for the isolated C-course demo, not learner evidence.
const examples: Record<string, { zh:string; en:string }> = {
  'demo-k1': { zh:'5 / 2 的两个操作数都是整数，结果为 2。\n改成 5.0 / 2，结果为 2.5。', en:'Both operands in 5 / 2 are integers, so the result is 2.\nWith 5.0 / 2, the result is 2.5.' },
  'demo-k2': { zh:'int count = 0; 在创建变量时给出初值。\n后面的 count = 3; 是赋值，不是再次初始化。', en:'int count = 0; supplies the initial value when the variable is created.\nA later count = 3; is assignment, not another initialization.' },
  'demo-k3': { zh:'若两个 int 相乘，乘法先按 int 计算。\n即使结果存入 long long，也应在乘法前转换：\nlong long result = (long long)a * b;', en:'Multiplying two int values performs int arithmetic first.\nConvert before multiplying, even when storing into long long:\nlong long result = (long long)a * b;' },
  'demo-k4': { zh:'if (0) 不会进入该分支。\nif (-1) 会进入该分支，因为 -1 是非零值。', en:'if (0) does not enter the branch.\nif (-1) does enter it because -1 is nonzero.' },
  'demo-k5': { zh:'if (x == 3) 比较 x 是否等于 3。\nx = 3 则会把 3 赋给 x。', en:'if (x == 3) checks whether x equals 3.\nx = 3 assigns 3 to x instead.' },
  'demo-k6': { zh:'if (a) {\n  if (b) { doSomething(); }\n  else { doOtherThing(); }\n}\n这里的 else 属于内层 if (b)。', en:'if (a) {\n  if (b) { doSomething(); }\n  else { doOtherThing(); }\n}\nThe else belongs to the inner if (b).' },
  'demo-k7': { zh:'以 60 分为及格线：\nx < 60　→ 不及格\nx ≥ 60　→ 及格\n\n代入 59、60、61，三个值都能归入唯一的分支。', en:'With a passing score of 60:\nx < 60  → fail\nx ≥ 60  → pass\n\nTest 59, 60, and 61: each belongs to exactly one branch.' },
  'demo-k8': { zh:'for (int i = 0; i < 3; i++)\n其中 int i = 0 只在进入这次循环时执行一次，不会每轮重置 i。', en:'for (int i = 0; i < 3; i++)\nHere int i = 0 runs once on entering the loop. It does not reset i each iteration.' },
  'demo-k9': { zh:'int i = 3;\nwhile (i < 3) { i++; }\n第一次检查条件就不成立，循环体一次也不执行。', en:'int i = 3;\nwhile (i < 3) { i++; }\nThe first condition is false, so the body never runs.' },
  'demo-k10': { zh:'for (int i = 0; i < 3; i++)\n循环体依次看到 i 为 0、1、2；每轮循环体结束后才执行 i++。', en:'for (int i = 0; i < 3; i++)\nThe body sees i as 0, 1, then 2. The i++ update follows each body execution.' },
}

export function demoLearningContent(locale:'zh'|'en') {
  return Object.fromEntries(Object.entries(examples).map(([id, example]) => [id, {
    example:example[locale],
    ...(id === 'demo-k7' ? { rule: locale === 'zh' ? '每个边界值必须且只能落入一个分支，不能遗漏，也不能重复归类。' : 'Every boundary value must belong to exactly one branch, with no gaps or overlaps.' } : {}),
  }]))
}
