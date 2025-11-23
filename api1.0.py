import os
import sys
import uuid
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import torch
import logging
from pydantic import BaseModel as PydanticBaseModel
from openai import OpenAI

# 确保这些路径和包在你运行 main.py 的目录下是可访问的
sys.path.append(sys.path[0] + r"/../") 
# 注意：如果运行报错找不到模块，可能需要将上面的 sys.path 调整为绝对路径或根据你的目录结构调整
from os.path import join as pjoin
from models import *
from collections import OrderedDict
from configs import get_config
from utils.plot_script import *
from utils.preprocess import *
from utils import paramUtil
import lightning as L
import scipy.ndimage.filters as filters
import copy
import numpy as np

# --- 你的类定义 (保持不变) ---
class LitGenModel(L.LightningModule):
    def __init__(self, model, cfg):
        super().__init__()
        self.cfg = cfg
        self.automatic_optimization = False
        self.save_root = pjoin(self.cfg.GENERAL.CHECKPOINT, self.cfg.GENERAL.EXP_NAME)
        self.model_dir = pjoin(self.save_root, 'model')
        self.meta_dir = pjoin(self.save_root, 'meta')
        self.log_dir = pjoin(self.save_root, 'log')
        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.meta_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        self.model = model
        self.normalizer = MotionNormalizer()

    def plot_t2m(self, mp_data, result_path, caption):
        mp_joint = []
        for i, data in enumerate(mp_data):
            if i == 0:
                joint = data[:,:22*3].reshape(-1,22,3)
            else:
                joint = data[:,:22*3].reshape(-1,22,3)
            mp_joint.append(joint)
        # 注意：确保 plot_3d_motion 不会阻塞太久，或者在无GUI环境下能运行
        plot_3d_motion(result_path, paramUtil.t2m_kinematic_chain, mp_joint, title=caption, fps=30)

    def generate_one_sample(self, prompt, name):
        self.model.eval()
        batch = OrderedDict({})
        batch["motion_lens"] = torch.zeros(1,1).long().cuda()
        batch["prompt"] = prompt
        window_size = 210
        motion_output = self.generate_loop(batch, window_size)
        
        # 确保输出目录存在
        output_dir = "results"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
        result_path = f"{output_dir}/{name}.mp4"

        self.plot_t2m([motion_output[0], motion_output[1]],
                      result_path,
                      batch["prompt"])
        return result_path # 修改：返回生成文件的路径以便 API 使用

    def generate_loop(self, batch, window_size):
        prompt = batch["prompt"]
        batch = copy.deepcopy(batch)
        batch["motion_lens"][:] = window_size
        sequences = [[], []]
        batch["text"] = [prompt]
        batch = self.model.forward_test(batch)
        motion_output_both = batch["output"][0].reshape(batch["output"][0].shape[0], 2, -1)
        motion_output_both = self.normalizer.backward(motion_output_both.cpu().detach().numpy())
        for j in range(2):
            motion_output = motion_output_both[:,j]
            joints3d = motion_output[:,:22*3].reshape(-1,22,3)
            joints3d = filters.gaussian_filter1d(joints3d, 1, axis=0, mode='nearest')
            sequences[j].append(joints3d)
        sequences[0] = np.concatenate(sequences[0], axis=0)
        sequences[1] = np.concatenate(sequences[1], axis=0)
        return sequences

def build_models(cfg):
    if cfg.NAME == "InterGen":
        model = InterGen(cfg)
    return model

# --- FastAPI 封装部分 ---

# 定义请求体结构
class MotionRequest(BaseModel):
    text: str

# 全局变量存储模型实例
litmodel = None

# 初始化加载函数
def load_model_logic():
    global litmodel
    print("Loading model config and weights...")
    # 这里的路径根据实际文件结构可能需要微调
    model_cfg = get_config("configs/model.yaml")
    infer_cfg = get_config("configs/infer.yaml")

    model = build_models(model_cfg)

    if model_cfg.CHECKPOINT:
        # 确保路径存在
        if not os.path.exists(model_cfg.CHECKPOINT):
            print(f"Warning: Checkpoint not found at {model_cfg.CHECKPOINT}")
        else:
            ckpt = torch.load(model_cfg.CHECKPOINT, map_location="cpu")
            for k in list(ckpt["state_dict"].keys()):
                if "model" in k:
                    ckpt["state_dict"][k.replace("model.", "")] = ckpt["state_dict"].pop(k)
            model.load_state_dict(ckpt["state_dict"], strict=False)
            print("Checkpoint state loaded!")

    # 初始化 Lightning 模型并移至 GPU
    litmodel = LitGenModel(model, infer_cfg).to(torch.device("cuda:0"))
    print("Model loaded successfully!")

# 定义清理临时文件的函数
def remove_file(path: str):
    try:
        os.remove(path)
    except Exception as e:
        print(f"Error removing file {path}: {e}")

# 创建 FastAPI 应用，并在启动时加载模型
app = FastAPI(on_startup=[load_model_logic])

@app.post("/generate_motion")
def generate_motion_endpoint(request: MotionRequest, background_tasks: BackgroundTasks):
    """
    输入文本，返回生成的 MP4 视频。
    """
    if not litmodel:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    # 1. 生成唯一的任务ID，防止文件名冲突
    task_id = str(uuid.uuid4())
    
    try:
        # 2. 调用模型推理
        # 注意：generate_one_sample 内部是在 results/ 目录下创建文件
        # 我们传入 task_id 作为 name，文件将是 results/{task_id}.mp4
        file_path = litmodel.generate_one_sample(request.text, task_id)
        
        # 3. 验证文件是否生成
        if not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Video generation failed")
        
        # 4. 设置后台任务：在响应发送给用户后，删除服务器上的临时视频文件
        background_tasks.add_task(remove_file, file_path)
        
        # 5. 返回文件流
        return FileResponse(
            path=file_path, 
            media_type="video/mp4", 
            filename=f"motion_{task_id}.mp4"
        )

    except Exception as e:
        logging.error(f"Error during generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- 翻译接口（千问） ----------------
class TranslateRequest(PydanticBaseModel):
    text: str
    target_lang: str = "English"


@app.post("/translate")
def translate_endpoint(req: TranslateRequest):
    """使用千问（Dashscope）的大模型翻译文本。

    环境变量：
      - DASHSCOPE_API_KEY: API Key（必需）
      - DASHSCOPE_BASE_URL: 可选，覆盖默认 base_url（如中国/新加坡地域）
    """
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")

    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        messages = [{"role": "user", "content": req.text}]
        translation_options = {"source_lang": "auto", "target_lang": req.target_lang}

        completion = client.chat.completions.create(
            model="qwen-mt-flash",
            messages=messages,
            extra_body={
                "translation_options": translation_options
            }
        )

        translated = None
        try:
            translated = completion.choices[0].message.content
        except Exception:
            # 兼容不同返回格式
            translated = getattr(completion.choices[0], "message", None) or getattr(completion.choices[0], "text", None)

        if not translated:
            raise HTTPException(status_code=502, detail="Translation service returned empty response")

        return {"translation": translated}

    except Exception as e:
        logging.exception("Translation API error")
        raise HTTPException(status_code=502, detail=str(e))

if __name__ == "__main__":
    # 启动服务
    uvicorn.run(app, host="0.0.0.0", port=8000)