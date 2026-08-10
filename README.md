# TOEFL Training System

出題訓練系統（以 TOEFL ITP 爲主）。

## Install

```bash
git clone git@github.com:Penguin-71630/toefl-trainer.git
cd toefl-trainer

# 如果使用 macOS 且套件環境是 Homebrew，必須要用 venv
python3 -m venv venv && source venv/bin/activate   

pip install -r requirements.txt
python init.py
```

## Launch

初次使用：

1. 先在 `.env` 內填入 `LLM_API_KEY`
  - 沒有 `LLM_API_KEY` 也能體驗這套系統，出題系統會從預先出好的 40 道題目中出題。
2. 啟動系統：
  ```bash
  python run.py
  ```

再次使用：
```bash
source venv/bin/activate && python run.py  # with `venv`
python run.py                              # without `venv`
```

## For Development

```bash
python run.py backend
```

則只跑 backend，API 文件在 `http://127.0.0.1:8000/docs`。


