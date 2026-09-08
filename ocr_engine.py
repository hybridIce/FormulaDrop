"""Local Pix2Text-MFR-1.5 inference using ONNX Runtime, without torch.
Preprocessing follows the model's DeiT processor configuration.
"""
import hashlib
import io
import json
import re
import time
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps
from tokenizers import Tokenizer

MODEL_DIR = Path(__file__).resolve().parent / 'models/mfr-1.5'


def normalize_latex(text):
    # The model sometimes wraps a starred operator in another mathop, which
    # loses the intended below/above limit placement in KaTeX.
    pattern = r"\\mathop\s*\{\s*\\operatorname\*\s*\{\s*([a-zA-Z ]+)\s*\}\s*\}"
    def unwrap(match):
        name = match.group(1).replace(' ', '')
        if name not in {'max','min','lim','sup','inf','argmax','argmin'}:
            return match.group(0)
        return r'\operatorname*{' + name + '}'
    return re.sub(pattern, unwrap, text)


class RecognitionLimitError(ValueError):
    pass


class FormulaOCR:
    name = 'Pix2Text MFR 1.5'

    def __init__(self, model_dir=MODEL_DIR, time_limit=12, max_tokens=384):
        self.time_limit = time_limit
        self.max_tokens = max_tokens
        self.cache = OrderedDict()
        self.last_cached = False
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.encoder = ort.InferenceSession(str(model_dir/'encoder_model.onnx'), opts, providers=['CPUExecutionProvider'])
        self.decoder = ort.InferenceSession(str(model_dir/'decoder_model.onnx'), opts, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(model_dir/'tokenizer.json'))
        self.processor = json.loads((model_dir/'preprocessor_config.json').read_text())
        self.generation = json.loads((model_dir/'generation_config.json').read_text())
        # Warm up both graphs once while health reports loading.
        context = self.encoder.run(None, {'pixel_values': np.ones((1,3,384,384), dtype=np.float32)})[0]
        self.decoder.run(None, {'input_ids':np.array([[1]], dtype=np.int64), 'encoder_hidden_states':context})

    def pixels(self, data):
        pic = Image.open(io.BytesIO(data)).convert('RGB')
        gray = np.array(pic.convert('L'))
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        coords = cv2.findNonZero(mask)
        if coords is None:
            raise ValueError('图片中没有可辨认的公式。')
        x, y, w, h = cv2.boundingRect(coords)
        pic = pic.crop((x,y,x+w,y+h))
        # Crop only outer blank space. Keep fine subscripts and superscripts.
        pic = ImageOps.expand(pic, border=max(4, round(min(w,h)*.08)), fill='white')
        size = self.processor['size']
        pic = pic.resize((size['width'],size['height']), Image.Resampling(self.processor['resample']))
        array = np.array(pic,dtype=np.float32) * self.processor['rescale_factor']
        array = (array-np.array(self.processor['image_mean'],dtype=np.float32))/np.array(self.processor['image_std'],dtype=np.float32)
        return np.ascontiguousarray(array.transpose(2,0,1)[None])

    def __call__(self, data):
        started = time.perf_counter()
        key = hashlib.sha256(data).digest()
        self.last_cached = key in self.cache
        if self.last_cached:
            self.cache.move_to_end(key)
            return self.cache[key], time.perf_counter()-started
        context = self.encoder.run(None, {'pixel_values':self.pixels(data)})[0]
        ids = np.array([[self.generation['decoder_start_token_id']]],dtype=np.int64)
        for _ in range(self.max_tokens):
            if time.perf_counter()-started > self.time_limit:
                raise RecognitionLimitError('识别超过 12 秒，已停止。请缩小到单个公式后重试。')
            logits = self.decoder.run(None, {'input_ids':ids, 'encoder_hidden_states':context})[0]
            token = int(logits[0,-1].argmax())
            if token == self.generation['eos_token_id']:
                text = normalize_latex(self.tokenizer.decode(ids[0].tolist(),skip_special_tokens=True).strip())
                if not text:
                    raise ValueError('没有识别到公式。')
                self.cache[key] = text
                if len(self.cache)>32:
                    self.cache.popitem(last=False)
                return text,time.perf_counter()-started
            ids = np.concatenate([ids,[[token]]],axis=1)
        raise RecognitionLimitError('公式过长或未能完整识别，请分成多个公式截图。')
