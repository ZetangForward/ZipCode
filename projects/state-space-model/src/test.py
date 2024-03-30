import os  
import sys
sys.path.append(os.getcwd())
import torch   
import hydra  
import lightning.pytorch as pl
from modelzipper.tutils import *
from utils import get_model_tokenizer, CustomDatamodule
from evaluate.evaluator import Evaluator

class Experiment(pl.LightningModule):
    def __init__(self, model, config, tokenizer=None, state="eval") -> None:
        super(Experiment, self).__init__()
        self.model = model
        self.model.eval()
        self.cfg = config
        self.tokenizer = tokenizer
        if hasattr(config.task, "inference_cfg"):  # what to save for task setting
            for key in config.task.inference_cfg:
                if isinstance(key, int):
                    key = str(key)
                setattr(self, key, config.task.inference_cfg[key])

        try:
            self.hold_graph = self.params['retain_first_backpass']
        except:
            pass

    @torch.no_grad()
    def predict_step(self, batch, batch_idx, dataloader_idx=None):

        input_ids = batch.pop("input_ids")
        # import pdb;pdb.set_trace()
        if "ar" in self.cfg.exp_task.lower():
            output = self.model(input_ids).logits.max(-1)[1]
            # import pdb; pdb.set_trace()
            final_res = {}
            final_res['predictions'] = output[0]
            final_res['labels'] = batch.pop('label')
            # import pdb; pdb.set_trace()
        elif "longbench" in self.cfg.exp_task.lower():
            max_gen_len = batch.pop("max_generation_len")
            context_length = input_ids.shape[-1]
            if self.cfg.task.dataset.subtask == "samsum": 
                output = self.model.generate(
                    input_ids,
                    max_length=int(input_ids.size(-1) + max_gen_len),
                    num_beams=1,
                    do_sample=False,
                    temperature=1.0,
                    min_length=context_length+1,
                    eos_token_id=[self.tokenizer.eos_token_id, self.tokenizer.encode("\n", add_special_tokens=False)[-1]],
                )[0]
            else:
                output = self.model.generate(
                    input_ids,
                    max_length=int(input_ids.size(-1) + max_gen_len),
                    num_beams=1,
                    do_sample=False,
                    temperature=1.0,
                )[0]
            
            pred = self.tokenizer.decode(output[context_length:], skip_special_tokens=True)

            # import pdb;pdb.set_trace()
            final_res = {}
            # final_res['predictions'] = output[0]
            final_res['answers'] = pred
            final_res['labels'] = batch.pop('answers')

        else:
            output = self.model.generate(
                    input_ids, 
                    max_length=input_ids.size(-1) + self.cfg.task.other_cfgs.max_generation_length,
                    min_length=input_ids.size(-1) + 10, 
                    eos_token_id=self.tokenizer.eos_token_id, 
                )
            final_res = {}
            final_res['predictions'] = output[0]
        
        # if self.save_keys is not None:
        #     for key in self.save_keys:
        #         if key in batch:
        #             value = batch[key]
        #             if isinstance(value, torch.Tensor):
        #                 value = value.item()
        #             final_res[key] = value
        # import pdb;pdb.set_trace()
        return final_res

class CustomModel(nn.Module):
    def __init__(self, model) -> None:
        super().__init__()
        self.model = model
    
@hydra.main(config_path='../configs', config_name='test_config', version_base='1.1')
def main(config):

    print_c(OmegaConf.to_yaml(config), "yellow")
    model_root_dir = config.platform.hf_model_path
    save_root_dir = config.platform.result_path
    data_root_dir = config.platform.dataset_path

    # if use_custom_module 
    use_custom_module = False
    if hasattr(config.model, "use_custom_module"):
        use_custom_module = config.model.use_custom_module

    model, tokenizer = get_model_tokenizer(model_root_dir, config.model, use_custom_module=use_custom_module)
    custom_model = CustomModel(model)


    # load testing data
    if "longbench"  in config.exp_task:
        # subtask = [["qasper", "multifieldqa_en", "hotpotqa"], ["2wikimqa", "gov_report", "multi_news"], \
        #             ["musique", "trec", "triviaqa", "samsum"], ["passage_count", "passage_retrieval_en", "qmsum","narrativeqa"]]
        # subtask = [["qasper"]]
        subtask = [["narrativeqa", "qasper", "multifieldqa_en", "hotpotqa", "2wikimqa", "musique", "gov_report",  "qmsum" ,\
                    "multi_news", "trec", "triviaqa", "samsum", "passage_count", "passage_retrieval_en"]]
        # subtask = [["trec", "triviaqa", "samsum", "passage_count", "passage_retrieval_en", "qmsum","narrativeqa"]]
        if config.task.dataset.subtask == "None":
            subtask = subtask[0]    
        elif isinstance(config.task.dataset.subtask, list):
            subtask = config.task.dataset.subtask
    else:
        subtask =  [config.exp_task]


    for task in subtask:
        OmegaConf.set_struct(config, False)
        config.task.dataset.subtask = task 
        OmegaConf.set_struct(config, True)
        data_module = CustomDatamodule(config.task, data_root_dir, tokenizer)
        data_module.setup(stage='predict')

        # import pdb;pdb.set_trace()
        if config.model.load_model_state_dict :
            state_dict = torch.load(
                os.path.join(config.platform.hf_model_path, config.model.ckpt_path), 
                map_location='cuda'
            )
            # import pdb;pdb.set_trace()
            if state_dict.get('state_dict'):
                state_dict = state_dict['state_dict']

            try:
                custom_model.load_state_dict(state_dict, strict=True)
                model = custom_model.model
            except:
                model.load_state_dict(state_dict, strict=True)

        # load experiment (and model checkpoint)
        experiment = Experiment(model=model, config=config, tokenizer=tokenizer)
        
        tester = pl.Trainer(devices=config.experiment.device_num)

        b_t = time.time()
        # import pdb;pdb.set_trace()
      
        predictions = tester.predict(
            model=experiment,
            dataloaders=data_module.predict_dataloader(),
            return_predictions=True,
        )
    
        
        print_c(f"======= prediction end, begin to post process and save =======", "magenta")
        if task == config.exp_task: 
            save_path = os.path.join(save_root_dir, f"{config.experiment.results_save_dir}/")
            save_path=os.path.dirname(os.path.dirname(os.path.dirname(save_path)))
            save_final_path = os.path.join(save_root_dir, f"{config.experiment.results_save_dir}/predictions.pkl")
        else:
            save_path = os.path.join(save_root_dir, f"{config.experiment.results_save_dir}/")
            save_final_path = save_path + str(task)+ "_predictions.pkl"
        auto_save_data(predictions, save_final_path)
        print_c(f"save predictions to {save_final_path}, total cost time: {time.time() - b_t}", "magenta")

        eval = Evaluator(
            root_dir=save_root_dir, fpath=save_final_path, 
            data_path=os.path.join(data_root_dir, config.task.dataset.data_path), 
            task=config.exp_task,
            subtask=task if task!=config.exp_task else config.mark,
            tokenizer_name_or_path=None,
            value=None, save_evaluation_path=save_path,
            save_gen_res=True,
        )

    
   

if __name__ == '__main__':
    main()