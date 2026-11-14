"""Legendador de cena: Florence-2-base-ft em ONNX, carregado sob demanda.

O export separa o modelo em quatro grafos: vision_encoder (pixels -> 577 features),
embed_tokens (ids -> embeddings), encoder_model e decoder_model (ambos recebem
inputs_embeds, nao ids). Os features de imagem entram na frente dos embeddings do
texto, e o decoder e BART: comeca no token 2 e para no 2.

Pesos: models/captioner (baixe com tools/fetch_models.py captioner). Licenca: MIT (microsoft/Florence-2).
"""

import pathlib

import cv2
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

DIR = pathlib.Path(__file__).resolve().parents[2] / "models" / "captioner"
START = EOS = 2  # generation_config: decoder_start_token_id / eos_token_id
MEAN = np.array([0.485, 0.456, 0.406], np.float32) * 255
STD = np.array([0.229, 0.224, 0.225], np.float32) * 255
# O export espera a tarefa em linguagem natural (nao o token "<DETAILED_CAPTION>"): com o token
# cru o modelo responde "unanswerable".
PROMPTS = {
    "<CAPTION>": "What does the image describe?",
    "<DETAILED_CAPTION>": "Describe in detail what is shown in the image.",
    "<MORE_DETAILED_CAPTION>": "Describe with a paragraph what is shown in the image.",
}


def available():
    return (DIR / "onnx" / "decoder_model.onnx").exists()


def _providers():
    avail = ort.get_available_providers()
    return [p for p in ("DmlExecutionProvider", "CPUExecutionProvider") if p in avail]


class Captioner:
    def __init__(self, folder=DIR):
        self.tok = Tokenizer.from_file(str(folder / "tokenizer.json"))
        opts = ort.SessionOptions()
        opts.log_severity_level = 3

        def load(name):
            return ort.InferenceSession(str(folder / "onnx" / name), opts, providers=_providers())

        self.vision = load("vision_encoder.onnx")
        self.embed = load("embed_tokens.onnx")
        self.encoder = load("encoder_model.onnx")
        self.decoder = load("decoder_model.onnx")
        self.embed_name = self.embed.get_inputs()[0].name

    def _pixels(self, img):
        x = cv2.resize(img, (768, 768), interpolation=cv2.INTER_AREA)  # 768x768 fixo = 577 tokens
        x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32)
        return ((x - MEAN) / STD).transpose(2, 0, 1)[None]

    def caption(self, img, task="<MORE_DETAILED_CAPTION>", max_new=48):
        vis = self.vision.run(None, {self.vision.get_inputs()[0].name: self._pixels(img)})[0]
        ids = np.array([self.tok.encode(PROMPTS[task]).ids], np.int64)
        text = self.embed.run(None, {self.embed_name: ids})[0]
        emb = np.concatenate([vis, text], axis=1).astype(np.float32)
        mask = np.ones(emb.shape[:2], np.int64)
        enc = self.encoder.run(None, {"inputs_embeds": emb, "attention_mask": mask})[0]

        out = [START]
        for _ in range(max_new):
            de = self.embed.run(None, {self.embed_name: np.array([out], np.int64)})[0]
            logits = self.decoder.run(None, {"inputs_embeds": de, "encoder_hidden_states": enc,
                                            "encoder_attention_mask": mask})[0]
            nxt = int(logits[0, -1].argmax())
            if nxt == EOS:
                break
            out.append(nxt)
        return self.tok.decode(out[1:], skip_special_tokens=True).strip()
