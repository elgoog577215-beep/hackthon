import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# 读取转写数据
with open('/Users/qyao/Code/edu_ai_home/server/tests/chaoxing_transcript.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

transcript = data['result']['transcript']

# 计算每条的字数和语速
records = []
for seg in transcript:
    start = seg['start']
    end = seg['end']
    text = seg['text'].strip()
    duration = end - start
    char_count = len(text)
    # 过滤掉过短的噪声片段（如只有1-2个字且时长很长的，可能是静音被误识别）
    if duration > 0:
        speed = char_count / duration
    else:
        speed = 0
    records.append({
        'start': start,
        'end': end,
        'duration': duration,
        'chars': char_count,
        'speed': speed,
        'text': text[:50] + '...' if len(text) > 50 else text,
    })

# 打印统计
valid = [r for r in records if r['duration'] > 0]
speeds = [r['speed'] for r in valid]
print(f"总片段数: {len(records)}")
print(f"有效片段数: {len(valid)}")
print(f"总时长: {transcript[-1]['end']/60:.1f} 分钟")
print(f"语速范围: {min(speeds):.2f} ~ {max(speeds):.2f} 字/秒")
print(f"平均语速: {np.mean(speeds):.2f} 字/秒")
print(f"中位语速: {np.median(speeds):.2f} 字/秒")

# 找出最快和最慢的片段
fastest = max(valid, key=lambda x: x['speed'])
slowest = min(valid, key=lambda x: x['speed'])
print(f"\n最快片段 ({fastest['speed']:.2f} 字/秒): [{fastest['start']:.1f}s - {fastest['end']:.1f}s] {fastest['text']}")
print(f"最慢片段 ({slowest['speed']:.2f} 字/秒): [{slowest['start']:.1f}s - {slowest['end']:.1f}s] {slowest['text']}")

# 过滤极端异常值：超过10字/秒的可能是误识别，低于0.1字/秒的是长停顿
filtered = [r for r in valid if 0.1 <= r['speed'] <= 8]
print(f"\n过滤后用于作图的片段数: {len(filtered)} (去除了 {len(valid)-len(filtered)} 个异常值)")

# 构建时间轴和语速序列（用每个片段的中点作为x轴）
x = [(r['start'] + r['end']) / 2 / 60 for r in filtered]  # 转换为分钟
y = [r['speed'] for r in filtered]

fig, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})

# 上图：语速散点 + 移动平均线
ax1 = axes[0]
ax1.scatter(x, y, s=15, alpha=0.4, color='steelblue', label='单片段语速')

# 移动平均窗口（约30秒 = 0.5分钟）
window_minutes = 1.0
window_size = max(5, int(window_minutes / (np.median([r['duration'] for r in filtered]) / 60)))
if len(y) >= window_size:
    y_smooth = np.convolve(y, np.ones(window_size)/window_size, mode='valid')
    x_smooth = x[window_size//2 : window_size//2 + len(y_smooth)]
    ax1.plot(x_smooth, y_smooth, color='darkred', linewidth=2, label=f'移动平均 (约{window_minutes}分钟窗口)')

ax1.axhline(y=np.median(y), color='green', linestyle='--', alpha=0.7, label=f'中位语速: {np.median(y):.2f}字/秒')
ax1.axhline(y=np.mean(y), color='orange', linestyle='--', alpha=0.7, label=f'平均语速: {np.mean(y):.2f}字/秒')
ax1.set_ylabel('语速 (字/秒)', fontsize=12)
ax1.set_title('超星视频字幕语速分析', fontsize=14)
ax1.legend(loc='upper right')
ax1.grid(True, alpha=0.3)
ax1.set_ylim(0, max(y) * 1.1)

# 下图：每段字数柱状图
ax2 = axes[1]
colors = ['steelblue' if r['speed'] >= np.median(y) else 'coral' for r in filtered]
widths = [r['duration'] / 60 for r in filtered]
starts = [r['start'] / 60 for r in filtered]
ax2.bar(starts, [r['chars'] for r in filtered], width=widths, color=colors, alpha=0.6, edgecolor='none')
ax2.set_xlabel('时间 (分钟)', fontsize=12)
ax2.set_ylabel('字数', fontsize=12)
ax2.set_title('各时段说话字数 (蓝色=高于中位语速, 红色=低于中位语速)', fontsize=12)
ax2.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
output_path = '/Users/qyao/Code/edu_ai_home/server/tests/speech_rate_chart.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"\n图表已保存: {output_path}")

# 同时输出CSV供查看
csv_path = '/Users/qyao/Code/edu_ai_home/server/tests/speech_rate_data.csv'
with open(csv_path, 'w', encoding='utf-8') as f:
    f.write('start_time,end_time,duration_s,chars,speed_chars_per_sec,text\n')
    for r in filtered:
        text_escaped = r['text'].replace('"', '""')
        f.write(f"{r['start']:.2f},{r['end']:.2f},{r['duration']:.2f},{r['chars']},{r['speed']:.2f},\"{text_escaped}\"\n")
print(f"数据已保存: {csv_path}")
