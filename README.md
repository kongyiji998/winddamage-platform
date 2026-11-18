# 基于多模态大模型的风电塔灾损测算平台

平台支持指定风机的单图与批量评估，在风场总览中展示病害部位和结构化报告，并支持本地历史记录及 PDF、Markdown、CSV 导出。

## 预览界面

源码附带风场场景及内置巡检样例。仅预览界面时，安装 FastAPI 和 Uvicorn 即可。在项目根目录运行以下命令。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install fastapi uvicorn
python -m uvicorn preview_ui:create_preview_app --factory --host 127.0.0.1 --port 7861
```

浏览器打开[风场总览](http://127.0.0.1:7861/screen#farm)。预览模式可查看内置样例和页面布局。

## 运行真实评估

1. 准备 Linux 和 Python 推理环境。已验证的环境为 Python 3.12 和 NVIDIA RTX 4090，依赖版本见 `requirements.txt`。
2. 将自行提供的完整 Hugging Face 格式模型放入项目根目录的 `qwen3.5-4b/`。目录需包含微调权重及其索引、模型配置、分词器、图像处理配置和对话模板。
3. 在已安装依赖的环境中，从项目根目录启动平台。

```bash
bash start.sh --open
```

启动脚本优先使用 `~/.venvs/winddamage-infer/bin/python`，其次使用当前环境的 Python。默认打开[本机评估平台](http://127.0.0.1:7860/screen#farm)。在新环境可先运行 `python -m pip install -r requirements.txt`。首次评估会将模型加载到设备。

评估记录与归档图片分别存放在本机 `history.db` 和 `persisted_images/`，备份时请一同保存。
