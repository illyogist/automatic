import json
import torch
import transformers
import transformers.dynamic_module_utils
from PIL import Image
from modules import shared, devices, errors


processor = None
model = None
loaded: str = None
vlm_models = {
    "MS Florence 2 Base": "microsoft/Florence-2-base", # 0.5GB
    "MS Florence 2 Large": "microsoft/Florence-2-large", # 1.5GB
    "MiaoshouAI PromptGen 1.5 Base": "MiaoshouAI/Florence-2-base-PromptGen-v1.5@c06a5f02cc6071a5d65ee5d294cf3732d3097540", # 1.1GB
    "MiaoshouAI PromptGen 1.5 Large": "MiaoshouAI/Florence-2-large-PromptGen-v1.5@28a42440e39c9c32b83f7ae74ec2b3d1540404f0", # 3.3GB
    "MiaoshouAI PromptGen 2.0 Base": "MiaoshouAI/Florence-2-base-PromptGen-v2.0", # 1.1GB
    "MiaoshouAI PromptGen 2.0 Large": "MiaoshouAI/Florence-2-large-PromptGen-v2.0", # 3.3GB
    "CogFlorence 2.0 Large": "thwri/CogFlorence-2-Large-Freeze", # 1.6GB
    "CogFlorence 2.2 Large": "thwri/CogFlorence-2.2-Large", # 1.6GB
    "Moondream 2": "vikhyatk/moondream2", # 3.7GB
    "GIT TextCaps Base": "microsoft/git-base-textcaps", # 0.7GB
    "GIT VQA Base": "microsoft/git-base-vqav2", # 0.7GB
    "GIT VQA Large": "microsoft/git-large-vqav2", # 1.6GB
    "BLIP Base": "Salesforce/blip-vqa-base", # 1.5GB
    "BLIP Large": "Salesforce/blip-vqa-capfilt-large", # 1.5GB
    "ViLT Base": "dandelin/vilt-b32-finetuned-vqa", # 0.5GB
    "Pix Textcaps": "google/pix2struct-textcaps-base", # 1.1GB
}
vlm_prompts = [
    '<CAPTION>',
    '<DETAILED_CAPTION>',
    '<MORE_DETAILED_CAPTION>',
    '<CAPTION_TO_PHRASE_GROUNDING>',
    '<OD>',
    '<DENSE_REGION_CAPTION>',
    '<REGION_PROPOSAL>',
    '<OCR>',
    '<OCR_WITH_REGION>',
    '<ANALYZE>',
    '<GENERATE_TAGS>',
    '<MIXED_CAPTION>',
    '<MIXED_CAPTION_PLUS>',
]


def git(question: str, image: Image.Image, repo: str = None):
    global processor, model, loaded # pylint: disable=global-statement
    if model is None or loaded != repo:
        shared.log.debug(f'Interrogate load: vlm="{repo}"')
        model = transformers.GitForCausalLM.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        processor = transformers.GitProcessor.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        loaded = repo
    model.to(devices.device, devices.dtype)
    pixel_values = processor(images=image, return_tensors="pt").pixel_values
    git_dict = {}
    git_dict['pixel_values'] = pixel_values.to(devices.device, devices.dtype)
    if len(question) > 0:
        input_ids = processor(text=question, add_special_tokens=False).input_ids
        input_ids = [processor.tokenizer.cls_token_id] + input_ids
        input_ids = torch.tensor(input_ids).unsqueeze(0)
        git_dict['input_ids'] = input_ids.to(devices.device)
    with devices.inference_context():
        generated_ids = model.generate(**git_dict)
    response = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    return response


def blip(question: str, image: Image.Image, repo: str = None):
    global processor, model, loaded # pylint: disable=global-statement
    if model is None or loaded != repo:
        shared.log.debug(f'Interrogate load: vlm="{repo}"')
        model = transformers.BlipForQuestionAnswering.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        processor = transformers.BlipProcessor.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        loaded = repo
    model.to(devices.device, devices.dtype)
    inputs = processor(image, question, return_tensors="pt")
    inputs = inputs.to(devices.device, devices.dtype)
    with devices.inference_context():
        outputs = model.generate(**inputs)
    response = processor.decode(outputs[0], skip_special_tokens=True)
    return response


def vilt(question: str, image: Image.Image, repo: str = None):
    global processor, model, loaded # pylint: disable=global-statement
    if model is None or loaded != repo:
        shared.log.debug(f'Interrogate load: vlm="{repo}"')
        model = transformers.ViltForQuestionAnswering.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        processor = transformers.ViltProcessor.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        loaded = repo
    model.to(devices.device)
    inputs = processor(image, question, return_tensors="pt")
    inputs = inputs.to(devices.device)
    with devices.inference_context():
        outputs = model(**inputs)
    logits = outputs.logits
    idx = logits.argmax(-1).item()
    response = model.config.id2label[idx]
    return response


def pix(question: str, image: Image.Image, repo: str = None):
    global processor, model, loaded # pylint: disable=global-statement
    if model is None or loaded != repo:
        shared.log.debug(f'Interrogate load: vlm="{repo}"')
        model = transformers.Pix2StructForConditionalGeneration.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        processor = transformers.Pix2StructProcessor.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        loaded = repo
    model.to(devices.device)
    if len(question) > 0:
        inputs = processor(images=image, text=question, return_tensors="pt").to(devices.device)
    else:
        inputs = processor(images=image, return_tensors="pt").to(devices.device)
    with devices.inference_context():
        outputs = model.generate(**inputs)
    response = processor.decode(outputs[0], skip_special_tokens=True)
    return response


def moondream(question: str, image: Image.Image, repo: str = None):
    global processor, model, loaded # pylint: disable=global-statement
    if model is None or loaded != repo:
        shared.log.debug(f'Interrogate load: vlm="{repo}"')
        model = transformers.AutoModelForCausalLM.from_pretrained(
            repo,
            revision="2024-08-26",
            trust_remote_code=True,
            cache_dir=shared.opts.hfcache_dir
        )
        processor = transformers.AutoTokenizer.from_pretrained(repo, cache_dir=shared.opts.hfcache_dir)
        loaded = repo
        model.eval()
    model.to(devices.device, devices.dtype)
    if len(question) < 2:
        question = "Describe the image."
    question = question.replace('<', '').replace('>', '')
    encoded = model.encode_image(image)
    with devices.inference_context():
        response = model.answer_question(encoded, question, processor)
    return response


def florence(question: str, image: Image.Image, repo: str = None, revision: str = None):
    global processor, model, loaded # pylint: disable=global-statement
    _get_imports = transformers.dynamic_module_utils.get_imports
    def get_imports(f):
        R = _get_imports(f)
        if "flash_attn" in R:
            R.remove("flash_attn") # flash_attn is optional
        return R
    if model is None or loaded != repo:
        shared.log.debug(f'Interrogate load: vlm="{repo}"')
        transformers.dynamic_module_utils.get_imports = get_imports
        model = transformers.AutoModelForCausalLM.from_pretrained(repo, trust_remote_code=True, revision=revision, cache_dir=shared.opts.hfcache_dir)
        processor = transformers.AutoProcessor.from_pretrained(repo, trust_remote_code=True, revision=revision, cache_dir=shared.opts.hfcache_dir)
        transformers.dynamic_module_utils.get_imports = _get_imports
        loaded = repo
        model.eval()
    model.to(devices.device, devices.dtype)
    if question.startswith('<'):
        task = question.split('>', 1)[0] + '>'
    else:
        task = '<MORE_DETAILED_CAPTION>'
        # question = task + question
    inputs = processor(text=task, images=image, return_tensors="pt")
    input_ids = inputs['input_ids'].to(devices.device)
    pixel_values = inputs['pixel_values'].to(devices.device, devices.dtype)
    with devices.inference_context():
        generated_ids = model.generate(
            input_ids=input_ids,
            pixel_values=pixel_values,
            max_new_tokens=shared.opts.interrogate_vlm_max_length,
            num_beams=shared.opts.interrogate_vlm_num_beams,
            do_sample=False
        )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        response = processor.post_process_generation(generated_text, task="task", image_size=(image.width, image.height))
    if 'task' in response:
        response = response['task']
    if 'answer' in response:
        response = response['answer']
    if isinstance(response, dict):
        response = json.dumps(response)
    response = response.replace('\n', '').replace('\r', '').replace('\t', '').strip()
    return response


def interrogate(question, image, model_name):
    if isinstance(image, list):
        image = image[0] if len(image) > 0 else None
    if isinstance(image, dict) and 'name' in image:
        image = Image.open(image['name'])
    if image is None:
        return ''
    try:
        vqa_model = vlm_models.get(model_name, None)
        revision = None
        if '@' in vqa_model:
            vqa_model, revision = vqa_model.split('@')
        if image is None:
            answer = 'no image provided'
            return answer
        if model_name is None:
            answer = 'no model selected'
            return answer
        if vqa_model is None:
            answer = f'unknown: model={model_name} available={vlm_models.keys()}'
            return answer
        if 'git' in vqa_model.lower():
            answer = git(question, image, vqa_model)
        elif 'vilt' in vqa_model.lower():
            answer = vilt(question, image, vqa_model)
        elif 'blip' in vqa_model.lower():
            answer = blip(question, image, vqa_model)
        elif 'pix' in vqa_model.lower():
            answer = pix(question, image, vqa_model)
        elif 'moondream2' in vqa_model.lower():
            answer = moondream(question, image, vqa_model)
        elif 'florence' in vqa_model.lower():
            answer = florence(question, image, vqa_model, revision)
        else:
            answer = 'unknown model'
    except Exception as e:
        errors.display(e, 'VQA')
        answer = 'error'
    if shared.opts.interrogate_offload and model is not None:
        model.to(devices.cpu)
    devices.torch_gc()
    return answer
