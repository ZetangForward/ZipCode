deepspeed --num_gpus 8 \
    --num_nodes 3 \
    --master_addr worker-0 \
    --master_port 6429 \
    --hostfile "/workspace/zecheng/modelzipper/projects/custom_llama/configs/machine/hostfile_v24" \
    icon-shop/train.py \
    --model_name_or_path "/zecheng2/model_hub/open_llama_3b_v2" \
    --data_path "/zecheng2/svg/icon-shop/meta_data" \
    --output_dir "/zecheng2/vqllama/baselines/iconshop" \
    --num_train_epochs 40 \
    --model_max_length 1024 \
    --per_device_train_batch_size 24 \
    --per_device_eval_batch_size 24 \
    --gradient_accumulation_steps 1 \
    --evaluation_strategy "steps" \
    --eval_steps 80 \
    --greater_is_better False \
    --save_strategy "steps" \
    --load_best_model_at_end True \
    --save_steps 80 \
    --metric_for_best_model "loss" \
    --save_total_limit 10 \
    --learning_rate 3e-6 \
    --warmup_steps 20 \
    --logging_steps 1 \
    --dataloader_num_workers 20 \
    --lr_scheduler_type "cosine" \
    --report_to "tensorboard" \
    --gradient_checkpointing True \
    --deepspeed "/workspace/zecheng/modelzipper/projects/custom_llama/configs/deepspeed/stage3.json" \
    --fp16 True \
    --remove_unused_columns False;



