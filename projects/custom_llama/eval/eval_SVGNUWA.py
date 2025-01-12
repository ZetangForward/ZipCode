import torch
import clip
import sys
sys.path.append("/workspace/zecheng/modelzipper/projects/custom_llama")
from PIL import Image
from torchmetrics.multimodal.clip_score import CLIPScore
from torchmetrics.image.fid import FrechetInceptionDistance
from torchmetrics.multimodal import CLIPImageQualityAssessment
import edit_distance
import transformers
from tqdm import trange
from modelzipper.tutils import *
import gc
from rouge import Rouge 
import numpy as np
from models.vqvae import VQVAE


@torch.no_grad()
def calculate_fid(fid_metric, pred_images, golden_images, clip_model, clip_process, device):
    """
    a single tensor it should have shape (N, C, H, W). If a list of tensors, each tensor should have shape (C, H, W). C is the number of channels, H and W are the height and width of the image.
    
        imgs_dist1 = torch.randint(0, 200, (100, 3, 299, 299), dtype=torch.uint8)  
        imgs_dist2 = torch.randint(100, 255, (100, 3, 299, 299), dtype=torch.uint8)
        fid.update(imgs_dist1, real=True)
        fid.update(imgs_dist2, real=False)
    """
    pred_image_features, golden_image_features = [], []
    for i in trange(len(pred_images)):
        pred_image = clip_process(Image.open(pred_images[i])).to(device)
        golden_image = clip_process(Image.open(golden_images[i])).to(device)
        pred_image_features.append(pred_image)
        golden_image_features.append(golden_image)
    
    pred_images = torch.stack(pred_image_features, dim=0).to(dtype=torch.uint8)
    golden_images = torch.stack(golden_image_features, dim=0).to(dtype=torch.uint8)
    
    fid_metric.update(golden_images, real=True)  # N x C x W x H
    fid_metric.update(pred_images, real=False)
    score = fid_metric.compute().detach()
    return score

@torch.no_grad()
def calculate_clip_core(clip_process, clip_metric, pred_images, keywords_lst):
    """
        metric = CLIPScore(model_name_or_path="openai/clip-vit-base-patch16")
        score = metric(torch.randint(255, (3, 224, 224), generator=torch.manual_seed(42)), "a photo of a cat")
        score.detach()
    """
    avg_scores = []
    for i in trange(len(pred_images)):
        img = clip_process(Image.open(pred_images[i])).unsqueeze(0).to(device).to(dtype=torch.uint8)
        clip_score = clip_metric(img, keywords_lst[i]).detach()
        avg_scores.append(clip_score)
        
    return sum(avg_scores) / len(avg_scores)


def calculate_clip_image_quality(quality_metric, pred_images):
    """
        _ = torch.manual_seed(42)
        imgs = torch.randint(255, (2, 3, 224, 224)).float()
        metric = CLIPImageQualityAssessment(prompts=("quality"))
        metric(imgs)
    """
    pred_image_features, golden_image_features = [], []
    for i in trange(len(pred_images)):
        pred_image = clip_process(Image.open(pred_images[i])).to(device)
    pred_images = torch.stack(pred_image_features, dim=0).to(dtype=torch.uint8)
    quality_score = quality_metric(pred_images)
    return quality_score


def calculate_edit(tokenizer, gen_svg_paths, golden_svg_paths):
    preds = [tokenizer.tokenize(x) for x in gen_svg_paths]     
    avg_str_prd_len = sum([len(x) for x in preds]) / len(preds)
    golden = [tokenizer.tokenize(x) for x in golden_svg_paths]      
    distance = []
    for i in trange(len(preds)):
        sm = edit_distance.SequenceMatcher(a=preds[i], b=golden[i])
        distance.append(sm.distance())
    return sum(distance) / len(distance), avg_str_prd_len


def calculate_hps(image_lst1, image_lst2, key_lst, clip_model, clip_process,):
   
    image1 = clip_process(Image.open("image1.png")).unsqueeze(0).to(device)
    image2 = clip_process(Image.open("image2.png")).unsqueeze(0).to(device)
    images = torch.cat([image1, image2], dim=0)
    text = clip.tokenize(["your prompt here"]).to(device)

    with torch.no_grad():
        image_features = clip_model.encode_image(images)
        text_features = clip_model.encode_text(text)

        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        hps = image_features @ text_features.T


def cal_rouge(generated_svg_str, golden_svg_str):
    rouge = Rouge()
    generated_svg_str = [x[:5000] for x in generated_svg_str]
    golden_svg_str = [x[:5000] for x in golden_svg_str]
    import pdb; pdb.set_trace()
    scores = rouge.get_scores(generated_svg_str[:50], golden_svg_str[:50])
    return scores

def calculate_recall(pred_list, gold_list):
    # 计算交集的大小，即在pred_list出现的且在gold_list中也出现的唯一token ID的数量
    common_tokens = set(pred_list) & set(gold_list)
    true_positives = sum(min(pred_list.count(token), gold_list.count(token)) for token in common_tokens)

    # 计算gold_list中的总token数量
    total_relevant = len(gold_list)

    # 计算召回率
    recall = true_positives / total_relevant if total_relevant > 0 else 0
    
    return recall


class PluginVQVAE(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model


if __name__ == "__main__":
    
    vqvae_config = load_yaml_config("/workspace/zecheng/modelzipper/projects/custom_llama/configs/deepspeed/vqvae_config_v2.yaml")
    
    # init VQVAE
    block_kwargs = dict(
        width=vqvae_config.vqvae_conv_block.width, 
        depth=vqvae_config.vqvae_conv_block.depth, 
        m_conv=vqvae_config.vqvae_conv_block.m_conv,
        dilation_growth_rate=vqvae_config.vqvae_conv_block.dilation_growth_rate,
        dilation_cycle=vqvae_config.vqvae_conv_block.dilation_cycle,
        reverse_decoder_dilation=vqvae_config.vqvae_conv_block.vqvae_reverse_decoder_dilation
    )
    vqvae = VQVAE(vqvae_config, multipliers=None, **block_kwargs)
    plugin_vqvae = PluginVQVAE(vqvae)
    checkpoint = torch.load(vqvae_config.ckpt_path)  # load vqvae ckpt
    plugin_vqvae.load_state_dict(checkpoint['state_dict'])
    print_c("VQVAE loaded!", "green")
    vqvae = plugin_vqvae.model
    
    vqvae.eval().cuda()

    
    device =  "cuda:7"
    ROOT_DIR = "/zecheng2/vqllama/test_vq_seq2seq/test_flat_t5/epoch_8100"
    pred_res = []
    pred_tokens, golden_tokens = [], []
    for i in trange(1):
        cur_content = auto_read_data(os.path.join(ROOT_DIR, f"snap_{i}_results.pkl"))
        pred_res.extend(cur_content)
        
    print_c(f"total {len(pred_res)} samples", "green")
    for i in trange(len(pred_res)):
        item = pred_res[i]
        p_zs = plugin_vqvae.model.encode(item['generated_svg_path'].unsqueeze(0).cuda(), 0, 1)
        g_zs = plugin_vqvae.model.encode(item['raw_data'].unsqueeze(0).cuda(), 0, 1)
        pred_tokens.append(p_zs[0].cpu().tolist()[0])
        golden_tokens.append(g_zs[0].cpu().tolist()[0])
        
    golden_svg_path = [len(item['golden_svg_path']) for item in pred_res]
    generated_svg_path = [item['generated_svg_path'].size(0) for item in pred_res]
    text = [item['text'] for item in pred_res]
    raw_data = [item['raw_data'].size(0) for item in pred_res]

    str_svg_path = auto_read_data(os.path.join(ROOT_DIR, "svg_paths.jsonl"))
    metrics = {}
    
    r_svg_path = [x['r_svg_path'] for x in str_svg_path]
    p_svg_path = [x['p_svg_path'] for x in str_svg_path]
    g_svg_path = [x['g_svg_path'] for x in str_svg_path]
    r_svg_str = [x['r_svg_str'] for x in str_svg_path]
    g_svg_str = [x['g_svg_str'] for x in str_svg_path]
    p_svg_str = [x['p_svg_str'] for x in str_svg_path]
    
    fid_metric = FrechetInceptionDistance(feature=768).to(device)  # 768
    clip_metric = CLIPScore(model_name_or_path="openai/clip-vit-large-patch14").to(device)
    quality_metric = CLIPImageQualityAssessment(prompts=("quality",))
    clip_model, clip_process = clip.load("ViT-L/14", device=device)
    
    import pdb; pdb.set_trace()

    recalls = [calculate_recall(pred, golden) for pred, golden in zip(pred_tokens, golden_tokens)]
    recall = sum(recalls) / len(recalls)
    
    scores = cal_rouge(p_svg_str, r_svg_str)
    metrics['rouge_scores'] = scores
    
    ## cal nlp metrics
    t5_tokenizer = transformers.T5Tokenizer.from_pretrained("/zecheng2/model_hub/flan-t5-xl")
    edit_p, p_str_len = calculate_edit(t5_tokenizer, p_svg_str, r_svg_path)
    metrics['edit_p'] = edit_p
    metrics['p_str_len'] = p_str_len
    metrics['svg_token_length'] = sum(generated_svg_path) / len(generated_svg_path)
        
    
    
    ## cal image metrics
    
    
    PI_fid_res = calculate_fid(fid_metric, p_svg_path, r_svg_path, clip_model, clip_process, device)
    metrics['PI_fid_res'] = PI_fid_res
    
    PI_CLIP_SCORE = calculate_clip_core(clip_process, clip_metric, p_svg_path, text)
    metrics['PI_CLIP_SCORE'] = PI_CLIP_SCORE
    
    quality_score = calculate_clip_image_quality(quality_metric, p_svg_path)
    metrics['quality_score'] = quality_score
    
    print(metrics)
    
    exit()
    
    pi_res_len = [item['pi_res_len'] for item in data]
    pc_res_len = [item['pc_res_len'] for item in data]
    gt_res_len = [item['gt_res_len'] for item in data]
    pi_res_str = [item['pi_res_str'] for item in data]
    pc_res_str = [item['pc_res_str'] for item in data]
    gt_str = [item['gt_str'] for item in data]
    PI_RES_image_path = [item['PI_RES_image_path'] for item in data]
    PC_RES_image_path = [item['PC_RES_image_path'] for item in data]
    GT_image_path = [item['GT_image_path'] for item in data]

    
    # dict_keys(['text', 'p_svg_str', 'g_svg_str', 'r_svg_str', 'r_svg_path', 'p_svg_path', 'g_svg_path'])
    
    
    fid_metric = FrechetInceptionDistance(feature=768).to(device)  # 768
    clip_metric = CLIPScore(model_name_or_path="openai/clip-vit-large-patch14").to(device)
   
    quality_metric = CLIPImageQualityAssessment(prompts=("quality",))
    
    clip_model, clip_process = clip.load("ViT-L/14", device=device)
    
    # pred_images = [item['p_svg_path'] for item in data]
    # reconstruction_images = [item['r_svg_path'] for item in data]
    # golden_images = [item['g_svg_path'] for item in data]
    metrics = {}
    
    metrics['pi_res_len'] = sum(pi_res_len) / len(pi_res_len)
    metrics['pc_res_len'] = sum(pc_res_len) / len(pc_res_len)
    metrics['gt_res_len'] = sum(gt_res_len) / len(gt_res_len)
    
    PI_fid_res = calculate_fid(fid_metric, PI_RES_image_path, GT_image_path, clip_model, clip_process, device).cpu()
    PC_fid_res = calculate_fid(fid_metric, PC_RES_image_path, GT_image_path, clip_model, clip_process, device).cpu()
    
    metrics['PI_fid_res'] = PI_fid_res
    metrics['PC_fid_res'] = PC_fid_res
    
    PI_CLIP_SCORE = calculate_clip_core(clip_process, clip_metric, PI_RES_image_path, keys)
    PC_CLIP_SCORE = calculate_clip_core(clip_process, clip_metric, PC_RES_image_path, keys)
    
    metrics['PI_CLIP_SCORE'] = PI_CLIP_SCORE
    metrics['PC_CLIP_SCORE'] = PC_CLIP_SCORE
    
    # text metrics
    t5_tokenizer = transformers.T5Tokenizer.from_pretrained("/zecheng2/model_hub/flan-t5-xl")
    edit_score_pi, pi_str_len = calculate_edit(t5_tokenizer, pi_res_str, gt_str)
    edit_score_pc, pc_str_len = calculate_edit(t5_tokenizer, pc_res_str, gt_str)
    
    metrics['edit_score_pi'] = edit_score_pi
    metrics['edit_score_pc'] = edit_score_pc
    metrics['pi_str_len'] = pi_str_len
    metrics['pc_str_len'] = pc_str_len
    
    print(metrics)
    
    exit()
    clip_model2, _ = clip.load("ViT-L/14", device=device)
    params = torch.load("/zecheng2/evaluation/hpc.pt")['state_dict']
    clip_model2.load_state_dict(params)
    
    import pdb; pdb.set_trace()
    hps_score = calculate_hps(image_lst1, image_lst2, key_lst)

