"""Explicit, user-requested Codex edits to the three first-trial handouts.

This records editorial changes; it is not a Qwen generation or repair loop.
Original requests, responses, baseline facts and answer banks remain unchanged.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
from .pipeline import read,save,digest
from .handout_trial import TITLES,SECTIONS,project_applications,inspect,render


def block(kind,heading,text,keys,terms=(),example=None,diagnostic=None,applications=()):
    return {'kind':kind,'heading':heading,'text':text,'knowledge_keys':list(keys),'term_keys':list(terms),
            'example_key':example,'diagnostic_key':diagnostic,'application_keys':list(applications)}


def types_document(bundle):
    t=lambda *numbers:[f'K-T{n:02d}' for n in numbers]
    sections=[]
    def section(index,blocks):
        plan=bundle['sections'][index]
        sections.append({'key':plan['key'],'title':plan['title'],'blocks':blocks})
    section(0,[
        block('explanation','先识别字面量的类型',
            '数值相同，不代表参与运算的类型相同。阅读一个表达式时，应先识别每个操作数的类型，再判断运算与结果转换。C17中，无后缀的十进制整数字面量在能由int表示时具有int类型；例如123符合这个条件。这里的“能表示”是必要条件，不能据此断言任意大的无后缀整数都使用int。\n\n本课使用的1U具有unsigned int类型；我们只用这个可表示的小值，不把结论推广到所有带U后缀的大整数字面量。无后缀的浮点字面量，如3.14，则具有double类型。先把整数、无符号整数与实浮点操作数辨认清楚，后续才能选择相应的转换规则。字面量类型由语言规则决定，不需要猜测语言设计者的动机。',
            t(1,2,3),['integer_literal']),
        block('explanation','整数提升看原类型的全部取值',
            '整数提升适用于语言规定需要提升、且原类型满足提升条件的场合，例如相应的较窄整数参与整数算术运算。判断依据是原类型的全部可取值范围：若int可以表示这些值，提升结果为int；否则为unsigned int。不能只看这一次变量恰好存了一个小值，就据此选择提升类型。\n\n因此，在已知int能够表示unsigned char全部值的环境中，两个unsigned char相加可以先在int中计算，不能直接当作按一个字节回绕。这条规则也不能简化为“任何不同类型的数运算前都先做整数提升”；浮点混合运算要按相应的通常算术转换规则判断。',
            t(4),['integer_promotion']),
        block('explanation','两种限定的共同类型规则',
            '通常算术转换用于确定相关算术操作的共同类型。本课先区分两种明确的情境：int与double运算时，int操作数转换为double，随后按double进行相应运算；int与unsigned int进行通常算术转换时，因为二者转换秩相同，int操作数转换为unsigned int。\n\n后一条不能推广为“任意有符号类型遇到任意无符号类型，都变成无符号类型”。例如比较int值-1与unsigned int值1，应先应用这里的转换方向，再按整数转无符号的规则确定转换值；不能直接套用负数一定小于正数的直觉。转换方向与转换后的具体数值，是推导中的两个步骤。',
            t(5,6),['usual_conversion','mod_conversion'])])
    section(1,[
        block('explanation','整数商向零截断',
            '在运算有定义的前提下，整数除法得到整数商，丢弃小数部分时朝零截断。正数商和负数商都遵守这条规则；向零截断不等于总是向下取整。分析负数例子时，先想清楚数学商位于哪两个整数之间，再选择靠近零的整数。以下只讨论有定义的运算，不对除零等情形预测正常数值结果。',
            t(7),['truncate']),
        block('worked_example','用负数区分截断方向',
            '例题计算-7/2。数学商是-3.5，向零截断后为-3，所以程序打印-3。若误用向下取整会得到-4；两者在正数例子中可能看不出区别，因此这里特意观察负数商。',t(7),['truncate'],example='E-T01'),
        block('explanation','接收类型不会反向改变右侧运算',
            '普通标量初始化或简单赋值，把右侧表达式已经求出的值转换为目标类型。左侧变量是double，并不会让右侧原本的int除法自动变成浮点除法。写题时可以把过程分成“右侧按自己的操作数类型求值”和“把所得值转换并存入目标”两步。\n\n这里说明的是值的转换与保存，不能进一步推断任意复杂赋值表达式的左右操作数总按“先右后左”的顺序求值。也不要把复合赋值和任意副作用表达式不加区分地套进这个简化说明。',t(8),['usual_conversion']),
        block('worked_example','double接收的是已经算好的值',
            '代码中7和2都是int，所以7/2先得到整数3。随后该值转换为double，x保存3.0，按一位小数打印为3.0。正确判断必须先看右侧除法的操作数类型，不能从左侧double倒推右侧得到了3.5。',t(8),[],example='E-T02'),
        block('explanation','显式转换的位置与副作用边界',
            '显式类型转换只作用于语法上指定的操作数。在(double)5/2中，显式转换先作用于5，随后与2进行浮点运算；在(double)(5/2)中，括号里的整数除法先完成，显式转换才作用于其结果。转换不能恢复此前已经丢掉的小数部分。\n\n单独读取变量并转换所得值，不会改变原变量的声明类型或存储值。如果操作数自身还带有自增、赋值等副作用，需要另外分析这些操作；“转换本身不改原变量”不等于“任何带转换符的整个表达式都没有副作用”。',t(9,10),['cast']),
        block('worked_example','对照转换发生在除法之前还是之后',
            '第一项先将5转为double再相除，得到2.5；第二项先算5/2得到2，再转换成2.0。输出顺序正是2.5、2.0。先圈定转换的操作数，再判断除法类型，比只记“出现double就保留小数”可靠。',t(9),['cast'],example='E-T03'),
        block('worked_example','转换结果与原变量分开',
            'n先被声明为int并保存10。(double)n产生用于初始化tmp的double值，但n只被读取。代码中的_Generic是辅助类型检查：此处n的类型为int就选取1，否则选取0；本讲只借它观察类型，不要求掌握其完整语法。输出的第一个1表示n仍是int，后面的10是n的存储值。它们验证的是原变量未被这次转换改动，而不是说所有带副作用的操作数都不改变状态。',t(10),['cast'],example='E-T04')])
    section(2,[
        block('explanation','整数目标能否表示原值',
            '整数转换到另一整数类型时，首先问目标类型能否表示原值。若能表示，数值保持不变，例如将100转换到能够表示100的short，结果仍为100。只有离开这个前提，才需要分别讨论无符号目标与有符号目标。\n\n若源值是整数、目标是有符号整数，而原值不能由目标表示，C17规定结果由实现定义，或者引发实现定义的信号。不能一律说成固定截位，也不能与有符号算术溢出的未定义行为混为一谈。实现定义意味着实现必须说明其选择，不意味着不同实现都给同一个结果。',t(12,13),['range','implementation_defined','undefined']),
        block('explanation','无符号整数的模转换',
            '整数转换为非_Bool无符号整数类型时，可用“模目标最大值加一”描述结果：选择目标范围内、与原整数同余的值。模数不是含混的“范围”，更不能漏掉最大值后面的加一。由此可知，整数-1转为unsigned int会得到UINT_MAX，不需要先假定unsigned int恰好是32位。\n\n这是整数到无符号整数的规则。不要把它拿去处理浮点转整数，也不要把无符号回绕与有符号溢出混为同一种行为。',t(11),['mod_conversion']),
        block('worked_example','打印的是比较结果，不是UINT_MAX本身',
            '本例把整数-1转换为unsigned int，再与UINT_MAX比较。程序打印1，表示这个相等比较成立；它并没有直接打印UINT_MAX的十进制数值。因此，即使不同实现的unsigned int位数不同，这个比较结论也不依赖某一个具体位数。',t(11),['mod_conversion'],example='E-T06'),
        block('explanation','有限实浮点转整数：先截断，再看上下界',
            '有限实浮点值转换为非_Bool整数类型时，先丢弃小数部分，方向仍是向零。随后必须检查截断后的整数部分能否由目标类型表示；若不能，行为未定义。这里比较的是目标实际上下界，不是把源值取绝对值后只比一个上限。\n\n例如(unsigned int)-1.5的整数部分为-1，unsigned int不能表示它，因此不能套用整数-1的模转换规则来给出UINT_MAX。另一方面，判断越界也不能只凭“原浮点值为负”这一特征，关键仍是截断后的整数部分是否可表示。越界情形在本讲作静态判断，不通过运行某次结果来证明规范。',t(14,15),['truncate','range','undefined']),
        block('worked_example','截断不是四舍五入',
            '本例只有一个转换：将有限浮点值3.999f转为int。整数部分3能够由int表示，所以向零截断后程序打印3，而不是四舍五入得到4。负值也遵循向零方向，但仍要检查截断后的整数部分是否可由目标类型表示；不能根据这个有定义的例子给越界转换指定正常输出。',t(14),['truncate'],example='E-T05')])
    section(3,[
        block('explanation','数值范围足够，不代表精确表示',
            '数值范围回答“大小是否容纳得下”，有效精度回答“相邻数值能否被区分”。整数转为实浮点时，即使整数处于目标浮点类型的数值范围内，也可能因为有效精度有限而无法精确表示。并非所有较大的整数都会丢失精度，仍要看该值能否由目标格式精确表示。\n\n本讲不假定所有C实现的double都有相同有效精度或采用相同的舍入选择。因此，讨论某个具体整数转换后精确得到哪个邻近值时，还需给出实现和格式条件；不能把本机一次结果推广为无条件的语言规则。',t(16),['range','precision']),
        block('diagnosis','同一个错答可能来自两种不同理解',
            '共同表现题把7/3的结果存入double后打印。正确结果是2.00，但A、B两种错误信念都会预测2.33，所以仅凭第一题不能区分它们。区分题去掉double接收变量，只在除法结束后显式转换结果：A仍把int除法误当作保留小数，预测2.33；按B的既定信念，没有左侧double接收情境，因而会预测正确的2.00。\n\n补救后再比较11/4在转换前后的位置差异，正确输出为2.00 2.75。复测改变数值并同时考查两个转换位置，防止只记住第一题的答案。这里的A/B是两种固定的错误模型；实际学习者还可能因为猜测、粗心或其他缺口给出同样结果，需要结合解释和更多证据判断。',t(7,8,9),['truncate','cast'],diagnostic='D-T'),
        block('summary','本讲的判断顺序',
            '处理数值转换题，可以依次检查：字面量与变量是什么类型；该运算是否需要整数提升或通常算术转换；显式转换具体作用于哪个操作数；表达式求得的值再怎样转换到接收类型。遇到边界时，将“整数到整数”和“有限实浮点到整数”分开，并区分数值范围与有效精度。\n\n始终保留适用条件：可表示的整数转换保持数值；整数转非_Bool无符号整数按目标最大值加一取模；整数转有符号且不能表示属于实现定义结果或信号；有限实浮点转非_Bool整数的整数部分不能表示则是未定义行为。规则相似不等于可以互换。',t(*range(1,17)),['integer_promotion','usual_conversion','cast','mod_conversion','undefined','implementation_defined','precision'])])
    return {'title':TITLES['types'],'knowledge_revision':bundle['knowledge_revision'],'terminology_revision':bundle['terminology_revision'],
        'introduction':'本讲把数值类型转换分成四个问题：操作数的类型如何确定，转换在表达式的哪个位置发生，目标类型能否表示所得值，以及表示是否精确。先掌握这些判断顺序，再用例题和自测检验，避免只根据变量名字或某次运行结果猜答案。',
        'sections':sections,'exercise_keys':['Q-T05','Q-T08','Q-T11','Q-T15','Q-T16'],'unresolved':[]}


def revise_if(doc):
    b=doc['sections']
    doc['introduction']='本讲区分两个问题：语法决定一条语句属于哪个分支，运行时的条件求值决定该分支是否执行。我们依次讨论标量条件、分支体边界、else配对和独立判断，并通过同源例题观察变量状态。以下均讨论普通结构化控制流，不考虑通过goto或标签跳入分支。'
    b[0]['blocks'][0]['text']='C17要求if的条件为标量表达式。本讲用整数和浮点数说明条件判断：与零比较不等为真，与零相等为假，因此非零负整数也为真；不需要“大于零”才能进入真分支。\n\n语法上，if的每个分支体是一条语句。这条语句可以是简单赋值、复合语句，也可以是整个嵌套if。若希望在同一个分支中顺序执行多条语句，可使用花括号形成复合语句。这里计算的是语句，不是文本行数：一条语句能跨多行，一行也能写多条语句。缩进可以帮助阅读，却不能替代语法边界。'
    b[0]['blocks'][1]['text']='执行if(n)时，程序根据当时n的值选择分支。n为-5，不等于零，因此进入真分支并输出T。这个例子只需要判断是否为零，不应将数值的正负号当成真假标准；这里描述的是程序执行语义，而不是要求编译器在编译时计算所有条件。'
    b[0]['blocks'][2]['heading']='一次执行只按当时条件选分支'
    b[0]['blocks'][4]['heading']='示例：分支体是一条语句'
    b[0]['blocks'][4]['text']='设有int a=0, x=0, y=0，执行if(a) x=1; y=2;。本例的真分支体仅是赋值语句x=1。因为a为0，这条赋值不执行；y=2是整条if之后的独立语句，仍会执行，所以最终y为2。即使这两条赋值写在同一行，控制范围也不会扩大；应以完整语句的语法边界判断，而不是数行数。'
    b[1]['blocks'][0]['text']='else结合到语法允许的、词法上最近的前面那个if。“语法允许”不可省略：需要尊重语句的完整结构，不能只搜索文本中最后出现的if。对于if(a) if(b) x=1; else x=2;，else属于内层if(b)。外层if的真分支体是整个内层if/else语句。\n\n先确定配对，再代入a、b的值分析路径。某个条件此时是真还是假，不会改变else在语法上归属于谁。这样可以避免根据希望执行的分支反过来猜配对。'
    b[1]['blocks'][2]['text']='只改变普通if/else代码的空白缩进，不改变词法记号、花括号、注释内容或语法结构，就不会改变else归属。将else视觉上对齐外层if，不能让原本配对内层if的else自动改属外层。\n\n这个结论只针对上述缩进调整，不能扩写成“C程序中的所有空格和换行都无意义”。字符串、注释和预处理等场景也不能按这条排版规则随意改动。本讲分析配对时，以合法程序的记号和结构为依据。'
    b[1]['blocks'].append(block('diagnosis','用缩进变化区分两种错误信念',
        '共同表现题和区分题都使用a=1、b=0、初始v=0；两题只改变else的视觉缩进，合法C程序的语法配对没有改变，所以正确输出都为2。共同题中，A按缩进配外层，B按“总归最外层”配对，两者都会错误地预测v仍为0。\n\n把else缩进到内层if同列后，A的既定规则会改为配内层并预测2，B仍按外层配对并预测0，这才产生区分。复测把外层条件设为假、初始v改为3；整个内层结构不执行，正确值仍为3，而按这两种错误规则会预测2。比较的是固定信念在不同情境中的结果，不是仅凭一次错答就给学习者贴标签。',
        ['K-I04','K-I06','K-I07'],['pairing'],diagnostic='D-I'))
    b[2]['blocks'][0]['text']='内层if/else能否执行，首先取决于包含它的外层分支是否被选中。外层没有选择该分支时，里面整个选择语句都不执行，内层else不能作为一个独立“兜底”从外部进入；即使这个嵌套选择语句没有额外花括号，也遵守相同原则。\n\n不要将它误读为“外层条件为假时总是直接跳到整条if之后”：如果外层本身还有else，应继续按外层的选择结构执行那个else。本结论只说明未被选中的那一部分内层代码不会执行，并限定在没有goto等跳入的普通控制流中。'
    b[2]['blocks'][2]['text']='if(cond);中的分号本身构成空语句，所以这个if的真分支体为空语句。紧跟其后的独立语句不因此受该if控制。对于这种普通执行情境，if(cond);与if(cond){}的分支都没有要执行的操作，执行效果可以相同，但语法类别不同：前者是空语句，后者是复合语句。\n\n检查控制范围时，应看完整语句和花括号，而不看“想把哪几行放进if”。例如条件为假时，如果后续赋值仍执行，先核对分号是否已经结束了那个空分支。'
    b[3]['blocks'][2]['text']='多个独立if会在控制流顺序到达它们时分别求值，前一个if命中不会自动跳过后一个条件。因此，在没有提前return等控制转移、操作均有定义的情况下，多个独立if可以先后命中。\n\n后续if读取的是自己求值时的当前状态。前一条if若修改了相关变量，后一条就会看到修改后的值；因此“彼此独立”并不意味着前面的状态修改不会影响后面的判断。与选择链比较时，应同时区分是否继续求值，以及继续求值时读到了什么状态。'
    b[3]['blocks'].append(block('summary','先定结构，再沿路径追踪状态',
        '分析if代码时，先按语法找出每个分支体和else的归属，再按实际条件选择执行路径。分支体是一条语句，复合语句可以包含多条语句；空语句和缩进都不能被误当成预期的控制范围。\n\n运行分析中，检查外层是否进入、当前条件何时读取、分支内修改了哪些变量。一次if执行不会因改值而补选另一分支；if/else-if选择链首命中后停止后续判断，独立if则在控制流到达时继续读取当前状态。任何简化判断都应保留“普通结构化执行、无额外跳转”的前提。',
        [f'K-I{i:02d}' for i in range(1,13)],['branch','compound','pairing','null_statement','chain','independent']))


def revise_for(doc):
    s=doc['sections']
    doc['introduction']='本讲按照“进入循环、判断、执行循环体、更新、再次判断”的顺序阅读for，再分析跳转如何改变路径。掌握基本顺序后，还要检查语句边界、变量作用域和数值范围，不能仅凭循环写在同一行或变量名字相同就推断其行为。以下采用C17，并把未定义行为仅作为静态边界讨论。'
    s[0]['blocks'][0]['text']='每次从入口正常进入for时，非空的初始化子句执行一次。它不会在同一次for运行的每一轮都重新执行；若以后再次从入口执行这条for语句，那是另一次进入。控制表达式负责决定是否进入循环体：每次入体前求值非空控制表达式，结果非零才入体。第一次判断就为假时，循环体执行零次。\n\n一次循环体正常完成后，先执行非空的迭代表达式，再回到控制表达式进行判断。这里的正常路径不包括break或return等提前转移；continue的路径随后单独说明。若完整执行了n次循环体，没有提前控制转移，并最终因条件为假退出，非空控制表达式共判断n+1次。多出的最后一次是假值检查，而不是又执行了一次循环体；不能把这个计数直接套到提前break的路径。'
    s[1]['blocks'][0]['text']='for头部的初始化子句、控制表达式、迭代表达式都可以省略，但分隔三部分的两个分号必须保留。省略初始化时，循环从已有合法状态开始；因此用到的变量必须已经正确初始化，不能把“没有初始化子句”误当成变量自动变为零。\n\n省略控制表达式时按非零常量处理，这只是说它不会因该条件变假而退出；循环体中的break或return仍可能结束相应执行。省略迭代表达式只表示该处没有更新操作，不会自动补出i++，状态仍可在循环体等位置改变。\n\n循环体在语法上是一条语句，复合语句可包含多条语句。for(...);中的分号是一条空语句，因而成为循环体；它后面的独立语句或块不属于这个循环体。单语句、复合语句和空语句的区别，与排版行数无关。'
    s[2]['blocks'][0]['text']='当最内层包围continue的循环是所述for时，continue跳过本轮剩余循环体，转到该for的推进位置，执行非空的迭代表达式，再判断条件；若第三部分省略，则没有该处更新可执行。break结束的是最内层包围它的循环或switch。如果实际被退出的是这个for，该次第三部分不会再执行。return则结束当前函数，不只是结束某一层循环；本讲运行片段位于void函数中，所以使用return;。\n\n对于直接位于for体内switch中的break，若没有更内层循环或switch包围它，它只结束该switch，随后继续执行switch之后尚余的循环体语句，不能直接跳过这些语句去更新。switch本身不是continue的目标：当没有更内层循环时，switch中的continue仍转到所述for的推进位置。判断目标应看实际包围结构，不是找最近的花括号。'
    s[2]['blocks'].insert(3,block('worked_example','return结束的是当前函数',
        '例题把输出update作为第三部分执行的观察标记。i=0时正常完成循环体，更新后打印一次update；i=1时执行return，sample函数立即结束，因此没有第二次update，也不会执行循环后的after。这个结果只用于说明该void函数片段的控制流，不能把return理解成只退出当前for。',
        ['K-F14'],[],example='E-F05'))
    s[2]['blocks'].insert(4,block('worked_example','退出switch后仍执行循环体余下语句',
        '两个case路径中的break都只结束当前switch。每一轮仍会继续执行其后的printf("A")，所以两轮共输出AA。若把break错误地理解成退出外层for，或者把switch后的语句直接跳过，就无法解释这个输出。',
        ['K-F15'],['body'],example='E-F07'))
    diagnosis=next(b for b in s[2]['blocks'] if b['kind']=='diagnosis')
    diagnosis['text']='共同表现题在i=3时先令i=6，再执行continue。正确路径还执行一次i++，所以最终输出i=7、hits=4；A把continue当break，B跳过更新直接判断，两者都会得到i=6、hits=4。仅凭这个共同错答无法区分A与B。\n\n区分题把触发时的赋值改成i=4。正确路径更新到5后还入体一次，得到6 5；A在赋值后直接退出，得到4 4；B跳过这次更新，于是会多执行i=4这一轮，最后得到6 6。两种错误信念在第二题中的差别，同时体现在退出位置或入体次数上。复测再改变上界，正确值为8 4，A/B均预测7 4。这里的程序特意让三种路径都能终止，不用无界运行去猜错误原因。'
    s[2]['blocks'].append(block('explanation','综合应用：内层转移后外层从哪里继续',
        '在外层for中嵌套内层for，且没有更内层循环或switch改变目标时，内层continue只推进该内层for：跳过内层本轮余下语句，执行它的第三部分，再检查它的条件。内层break则结束内层for，从内层for之后的语句继续执行外层循环体。它们都不会自动跳到外层for的更新位置，也不会自动结束外层for。\n\n完成一次分析可以依次标出：当前所在的最内层循环或switch，实际跳转的目标，目标之后仍会执行的语句，以及何时才轮到外层更新。若有return，才会按函数边界离开。这是一道组合应用，应引用continue和break等原子规则共同求解，而不是把整段复杂流程再当成一个不可拆的元知识。',
        ['K-F12','K-F13','K-F14'],['iteration','body'],applications=['application_nested_transfer']))
    s[3]['blocks'][0]['text']='for头部声明的变量，其名字作用域限定在相应for语句范围内，结束后不能在外部继续访问这个头部局部变量。若外层恰有另一个同名变量，之后读到的是外层对象，不能据此声称头部变量仍然可见。作用域讨论的是名字在哪里有效，不是简单地看两个变量是否拼写相同。\n\n变量若声明在循环外，且程序行为有定义，循环结束后保留的是实际退出路径上的当前值。不要把它笼统叫作“最后一次入体值”。例如前面的continue例题最终i为3，而break例题最终i为2：初值相同，但是否执行更新不同，退出状态就不同。循环体本身对变量的合法修改，也要一起纳入后续更新和判断。\n\nunsigned int的i>=0恒为真，不能只靠这个判断让倒序递减循环退出。从无符号零继续减一会按模回绕到最大值，回绕本身有定义；不代表所有无符号更新都回到最大值，也不代表i!=0等其他判断无效。显式break或return仍可改变退出路径。\n\n有符号边界要检查真正执行更新之前的值：若int类型的i此时仍等于INT_MAX，循环体没有将它改小，也没有提前跳出，继续执行i++会发生有符号整数溢出，属于未定义行为。如果循环体改变了i，或通过break/return使这次更新不再发生，就不能直接断言发生了同一溢出。此类边界只作静态判断，不运行未定义行为来推断规范。'
    s[3]['blocks'].append(block('summary','沿真实控制流逐步核对',
        '分析for时，先写清初始化、每次体前判断、循环体和更新的顺序，再检查是否有空语句或省略部分。正常退出的n+1次判断公式有明确前提，不能代替对break、continue、return的逐步追踪。\n\n遇到嵌套结构，先确定每条跳转实际作用的最内层目标，再继续追踪余下语句；遇到循环外的变量值，要按实际退出路径记录状态。最后检查数值与作用域边界：变量是否仍可见，循环体是否也修改控制变量，无符号判断能否终止，以及执行有符号更新前是否已处于不能再递增的值。',
        [f'K-F{i:02d}' for i in range(1,22)],['initializer','control','iteration','body','scope','wrap','overflow']))


def run(original,root,destination):
    root.mkdir(parents=True,exist_ok=True)
    if (root/'revision-manifest.json').exists():raise ValueError('revision_directory_already_exists')
    baseline=read(original/'knowledge.snapshot.json')
    save(root/'knowledge.snapshot.json',baseline);save(root/'terminology.json',read(original/'terminology.json'))
    documents={};sources={};reports={};changes={}
    for topic in ['types','if','for']:
        old=read(original/'calls'/(topic+'-handout')/'parsed.json')
        bundle=read(original/topic/'bundle.json')
        bundle['applications']=project_applications(baseline.get('applications',[]),{p['knowledge_id']:p['key'] for p in bundle['points']})
        doc=types_document(bundle) if topic=='types' else deepcopy(old)
        if topic=='if':revise_if(doc)
        if topic=='for':revise_for(doc)
        doc['editorial_revision']={'id':'handout-editorial-r1','author':'Codex','based_on_output_hash':digest(old),
                                  'reason':'用户明确要求修复引用、诊断、总结、术语及适用条件；不是千问重新生成。'}
        for section in doc['sections']:
            for i,b in enumerate(section['blocks'],1):b['block_id']=f"{topic}-r1-{section['key']}-{i:02d}"
        report=inspect(bundle,doc)
        if report['issues']:raise ValueError(report['issues'])
        save(root/topic/'bundle.json',bundle);save(root/topic/'revised.json',doc);save(root/topic/'structure-report.json',report)
        changes[topic]={'original_hash':digest(old),'revised_hash':digest(doc),'original_file':str(original/'calls'/(topic+'-handout')/'parsed.json'),
                        'editor':'Codex','type':'structure_and_content_edit' if topic=='types' else 'targeted_edits_and_additions'}
        render(bundle,doc,report,destination)
        documents[topic]=str(Path(topic)/'revised.json');reports[topic]=report
        sources[topic]=hashlib.sha256((original/'calls'/(topic+'-handout')/'parsed.json').read_bytes()).hexdigest()
        print(topic,len(report['explained_keys']),'points, no structural issues')
    save(destination/'知识基线.snapshot.json',baseline)
    save(root/'changes.json',changes);save(root/'structure-report.json',reports)
    save(root/'revision-manifest.json',{'origin':'user_requested_codex_editorial_revision','qwen_calls':0,
        'original_root':str(original),'original_response_sha256':sources,'document_paths':documents,
        'knowledge_revision':digest(baseline),'terminology_revision':digest(read(root/'terminology.json')),
        'revised_document_hashes':{t:digest(read(root/path)) for t,path in documents.items()}})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('original',type=Path);p.add_argument('root',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();run(a.original,a.root,a.destination)
