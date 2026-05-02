# 高考日语课堂小助手

一个面向 iPad 课堂使用的 Streamlit 小工具：课前上传试卷 PDF 和答案 PDF，按“知识运用/每篇阅读”分块调用 API 预处理，生成结构化解析包；课堂上点击句子或题号，直接秒出缓存解析，不在现场等待 API。

## 核心功能

- 跳过听力和作文，只处理日语知识运用与阅读理解
- 上传试卷 PDF、答案 PDF
- API OCR / 视觉识别 PDF 页面，适合扫描版试卷
- 也可本地提取 PDF 文字层，适合文字版 PDF
- AI 识别试卷结构并分块
- 按块预生成解析
  - 知识运用：按题组分析
  - 阅读理解：每篇文章 + 对应选择题作为一次分析
- 下载 / 上传 `.analysis.json` 解析包
- 课堂模式点击句子、题号直接显示解析
- 可选“临时追问”作为备用

## Streamlit Cloud Secrets

在 Streamlit Cloud 的 App secrets 里配置，不要提交到 GitHub：

```toml
OPENAI_API_KEY = "你的密钥"
OPENAI_BASE_URL = "https://tokenflux.dev/v1"
OPENAI_MODEL = "gpt-5.4"
APP_PASSWORD = "自己设置一个访问密码"
```

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

也可以用环境变量：

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://tokenflux.dev/v1"
export OPENAI_MODEL="gpt-5.4"
streamlit run app.py
```

## 使用流程

1. 打开 App，输入访问密码
2. 在“创建解析包”上传试卷 PDF 和答案 PDF
3. 选择“API OCR / 视觉识别（推荐）”，点击“提取/识别文本”
4. 点击“识别试卷结构”
5. 检查识别结果，取消勾选不需要的块
6. 点击“生成解析包”
7. 下载 `.analysis.json`
8. 上课时进入“课堂模式”，上传解析包，点击句子/题号查看解析
