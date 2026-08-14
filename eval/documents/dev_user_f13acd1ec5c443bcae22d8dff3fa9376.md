1、跑到开包检查环节就停了，输入模型的图片路径找不到？

2、之前万图跑不完是因为结果文件合并问题，现在已经修改完了，但是又出现了新问题。

3、结果不全，初步判断是因为项目只处理jpg后缀的图片文件





# 2.24

1、SAM2模型串行无并发，并发显存有OOM风险

2、重新跑一遍主流程，查看结果，今天结果中没有执行特定业务规则检查 (CATA/SERIE/BUMO)，因为SAM2模型2并发导致报错，该环节无结果



# 2.25

1、重跑QC之后，整个流程应该能跑通了，但是前端页面不显示？是不是使用代码触发的原因？和页面点击触发不一样？有待考证

2、检查为什么只处理jpg图片，在什么环节过滤了其他后缀的图片。目前只有 **Step 2**存在硬编码问题，修复待测试。

3、S25062392需要特定检查的是SERIE，但是经过Step2后，因为图片命名不匹配导致只处理jpg后缀图片，过滤了3千张左右，剩余四千张，结果文件中的serie_info字段是N/A。



# 2.26

1、发现recog_step1.csv的original_img_path字段，jpg图片命名后缀为：Original_resized，其他图片命名后缀为Original，原因好像是因为其他命名后缀的图片比较小？这就导致后续只对齐了jpg图片。

2、上述问题已经修补了，待测试。

3、已经重跑了25048618，需要验证两点，第一是S25062392项目跑完前端页面不显示，第二是只处理jpg图片的问题。



# 2.27

1、测试发现还有jpg的硬编码，导致处理jpeg的图片就报错了。

2、结果文件合并，qc_type字段内容合并，不再每个类型的问题都单独一行保存，单独保存的话如果有四类，文件大小为原来的4倍，这个需要和**前端沟通**一下是否需要修改，权衡利弊。

3、测试结果检查



# 3.2

1、测试项目整体可以运行，并且也不再缺失图片。

2、结果文件合并逻辑：qc_type字段内容合并。是否需要合并？合并的话需要前端同步修改

# 3.3

1、和佘鹏沟通，等待回复

# 3.4

1、他很忙，我想想办法。

2、- 正常流程 ：前端触发 -> 主流程运行（未合并字段）-> 回传 -> 前端正常显示 。
- 当前问题 ：
- 主流程运行（合并字段）-> 回传 -> 前端不显示 。
- 手动回传 （未合并字段，即正常格式） -> 前端也不显示 。

3、手动回传 （未合并字段，即正常格式） -> 前端显示了 。但是结果缺失………………

4、结果缺失是因为多模块数据流转中的 ID 格式不一致 导致的合并失败问题。
现在修复后用**S25042909**跑一下，这个项目只有**693张**图片，需要特定检查的是**BUMO**。
5、预处理会去除被识别为**翻拍/截图 、严重水印、过度裁剪、图片长宽比极度异常**这些图片。

​	图片分割会因无法识别产品主体（分割失败）而被跳过

​    Step2文件中的item_recog_projected_path数量是411证明了这一点

# 3.5

1、理解预处理和图片分割的细节

# 3.6

1、**S25042909**最终结果只有411张图片。

2、疑似因为只保留一个用户上传的第一张图片





# 3.9

如果不对user_id去重，后续流程会发生严重的“静默错误”和数据错乱。因为这不仅是多处理几条数据的问题，而是整个系统都会依赖于（user_id，q_id）的唯一性，如果打破这个会导致一下三个知名的问题。

1、字典映射被覆盖

​		代码中有大量逻辑是将DatetFrame转化为字典以便快速查找元数据。Python字典的Key必须唯一。如果有3条记录属于同一个user_id，to_dict()会自动执行“后盖前”的逻辑。结果字典中只会剩下最后一条记录的信息。当程序处理签两条图片时，查到的元数据会全部变成最后一条的，导致数据错乱，甚至把A图的结果匹配给B图的问卷信息。

2、中间文件被相互覆盖

​		系统在处理过程中会生成临时图片文件，比如旋转后的图、裁切图。文件名构建逻辑也依赖唯一性。如果同一个用户提交了多张图，系统会为他们生成完全相同的文件名。结果后处理的图片会直接覆盖掉先处理的图片，最终只得到一张图的处理结果，而且这张图可能对应了错误的元数据。

3、聚合逻辑失效

​		在后续的OCR的结果汇总阶段，代码通常假设一个user_id和q_id的组合之对应一个结果。pd.merge在遇到重复Key时会产生笛卡尔积，导致数据量爆炸性增长，例如三条元数据X三条识别结果=9条输出。以及在groupby聚合时，无法区分这多条数据谁是谁，导致逻辑混乱。





# 3.10

1、重构代码，不再去重。

2、查看结果，**S25042909**只增加到了458



# 3.12

1、分析罗列什么环节会过滤图片，这里过滤图片的意思指的不仅是将图片丢弃，也包括最终结果文件中不存在这个图片。





# 3.17

1、S26012295这个项目质检完了，但是结果只有两个图片，我查看数据有38张图，38个用户，你的结果中也是这样，但是页面只有两个显示，需要你和佘鹏沟通一下，看是哪里没有匹配上；

2、研究提出只做图片相似度的质检，但是我们图片相似度是附加的基础功能，相似度必检，但是同时得有其他类型的质检，比如cata/BUMO/...，你看看程序，这个能否只做相似度质检；





# 3.19

1、可以只做相似度检查了，不需要有其他类型的任何质检，但是需要测试联调一下

2、页面显示的问题佘鹏看了下 是dim那块传的被访者id有点不合规，在数据存储的时候对不上用户，所以导致数据出不来，他在修改，修改完会告诉我。





# 3.20

1、S26012295测试前端没有任何变化



# 3.23

1、前端显示没问题了

2、缺失图片是因为图片文件损坏



# 3.24

1、重跑测试S25062392



# 3.25

1、有三张图片无法读取，文件损坏或空文件。







# 3.27

1、构建离线安装包时，报错：
Downloading paramiko-3.5.1-py3-none-any.whl (227 kB)
Downloading peft-0.15.2-py3-none-any.whl (411 kB)
Downloading pillow-11.1.0-cp310-cp310-manylinux_2_28_x86_64.whl (4.5 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.5/4.5 MB 18.3 kB/s eta 0:00:00
Using cached pip-25.1.1-py3-none-any.whl (1.8 MB)
Downloading portalocker-3.1.1-py3-none-any.whl (19 kB)
Downloading propcache-0.3.1-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (206 kB)
Downloading protobuf-6.30.2-cp39-abi3-manylinux2014_x86_64.whl (316 kB)
Downloading psutil-7.0.0-cp36-abi3-manylinux_2_12_x86_64.manylinux2010_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl (277 kB)
Downloading pyarrow-19.0.1-cp310-cp310-manylinux_2_28_x86_64.whl (42.1 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 42.1/42.1 MB 19.9 kB/s eta 0:00:00
Downloading pycparser-2.22-py3-none-any.whl (117 kB)
Downloading pycryptodome-3.22.0-cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.3 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.3/2.3 MB 16.1 kB/s eta 0:00:00
Downloading pydantic_core-2.33.1-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.0 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.0/2.0 MB 15.2 kB/s eta 0:00:00
Downloading PyMySQL-1.1.1-py3-none-any.whl (44 kB)
Downloading PyNaCl-1.5.0-cp36-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.manylinux_2_24_x86_64.whl (856 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 856.7/856.7 kB 19.3 kB/s eta 0:00:00
Using cached pynndescent-0.5.13-py3-none-any.whl (56 kB)
Downloading pyodbc-5.3.0-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (322 kB)
Downloading pyparsing-3.2.5-py3-none-any.whl (113 kB)
Downloading PySocks-1.7.1-py3-none-any.whl (16 kB)
Downloading python_dateutil-2.9.0.post0-py2.py3-none-any.whl (229 kB)
Downloading pytz-2025.2-py2.py3-none-any.whl (509 kB)
Downloading PyYAML-6.0.2-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (751 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 751.2/751.2 kB 25.3 kB/s eta 0:00:00
Using cached rank_bm25-0.2.2-py3-none-any.whl (8.6 kB)
Downloading regex-2024.11.6-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (781 kB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 781.7/781.7 kB 18.6 kB/s eta 0:00:00
Downloading requests-2.32.3-py3-none-any.whl (64 kB)
Using cached urllib3-2.6.2-py3-none-any.whl (131 kB)
Downloading safetensors-0.5.3-cp38-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (471 kB)
Downloading scikit_learn-1.6.1-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (13.5 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 13.5/13.5 MB 19.1 kB/s eta 0:00:00
Downloading scipy-1.15.2-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (37.6 MB)
   ━━━━━━━━━━━━━╸━━━━━━━━━━━━━━━━━━━━━━━━━━ 12.8/37.6 MB 11.1 kB/s eta 0:37:22
WARNING: Connection timed out while downloading.

[notice] A new release of pip is available: 25.1.1 -> 26.0.1
[notice] To update, run: pip install --upgrade pip
error: incomplete-download

× Download failed because not enough bytes were received (12.8 MB/37.6 MB)
╰─> URL: https://files.pythonhosted.org/packages/de/3c/c96d904b9892beec978562f64d8cc43f9cca0842e65bd3cd1b7f7389b0ba/scipy-1.15.2-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl

note: This is an issue with network connectivity, not pip.
hint: Consider using --resume-retries to enable download resumption.
(aiqc) zixu@iZ2zedw7f80g877ypl0fnbZ:/data/ai_coding/AI-Coding$ 





# 3.30

1、接口文档





# 4.1

1、S25047229，这个项目，直接结果导出的文件中，开放题中，用户分组为1的这一组，组内相似度也是1，理解为相似度很高，可是看C列内容又没什么相似，丹尼尔提出的疑问，你帮看看是模型结果问题还是相似度的1表示的是不相似？





# 4.17

1、必选项改为可选项。查看代码

2、只跑增量的数据，强哥会提供给我数据库，然后只需要把跑完的对应的数据在数据库中标记一下就行。







# 5.8

1、网图、水印、雷同、过度裁剪、翻拍是必检项，改为可选项





# 5.12

QC自动化方式会议

1、从集团下载数据

2、数据存储到飞书





1、告诉龙虾原始数据位置

2、让龙虾下载后处理每一张图片

3、



# 5.13

网图、水印、雷同、过度裁剪、翻拍是必检项，改为可选项

SIM : 雷同卷（相似度）

STOCK : 网图/专业拍摄

WATERMARK : 水印

CROPPED : 过度裁剪

RESHOOT : 翻拍/屏幕图



# 5.14

1、同步trae修改的代码到服务器，并且测试。



# 5.15

1、同步trae修改的代码到服务器，并且测试。✅️





# 5.20

1、完善QC自动化生服测试流程



# 5.26

1、需要添加一个新的功能，首先，对结果的df中的user_id进行去重，然后到{sid}_rawdata表中对txt_run_log,img_run_log查找，这两个字段默认为空字段，如果这个项目（SID）的图片质检跑完了，就在对应的user_id的img_run_log字段添加一个Y，文本题也是同理，如果这两个字段本来就有Y了，那就跳过





# 5.28

1、在添加了对跑过一次的结果打标记的功能和修复了因底层合并遗漏图片名字段导致的 OCR 结果严重重复（笛卡尔积）的 Bug之后，前端页面的质检结果为空了，询问了佘鹏什么时候有时间看一下。✅️ 已解决



# 5.29

1、查看页面的结果和我自己跑的结果有无差异

