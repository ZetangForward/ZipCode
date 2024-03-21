export CUDA_VISIBLE_DEVICES=7
# mkdir -p /public/home/ljt/tzc/evaluation/AR_ywj/mamba-1_4b
MODEL_N=2048
MODEL_D=128
data_n_list="1024 2048 4096"
for DATA_N in $data_n_list
do
    data_d_list="48 96 192"
    for DATA_D in $data_d_list
    do
        JOB_ID=N${MODEL_N}_D${MODEL_D}-N${DATA_N}_D${DATA_D}

        # JOB_ID=N4096_D256-N4096_D128
        python mamba/test.py \
            model.ckpt_path=/nvme/zecheng/ckpt/AR_ywj-mamba-1_4b/version_MQAR_C8192_N${MODEL_N}_D${MODEL_D}/AR_ywj/MQAR_C8192_N${MODEL_N}_D${MODEL_D}/checkpoints/last.ckpt \
            model.load_model_state_dict=True \
            platform='amax_a100' \
            task='AR_ywj' \
            exp_task='AR_ywj' \
            job_id=$JOB_ID \
            task.dataset.processed_data_path=MQAR/test_C8192_N${DATA_N}_D${DATA_D}.pkl \
            task.dataset.input_seq_len=$DATA_N \
            task.dataset.num_kv_pairs=$DATA_D;

        wait

        python evaluate/evaluator.py \
            --task AR_ywj \
            --fpath /nvme/zecheng/evaluation/AR_ywj/mamba-1_4b/version_$JOB_ID/results/predictions.pkl \
            --save_evaluation_path /nvme/zecheng/evaluation/AR_ywj/mamba-1_4b/version_$JOB_ID/results/eval.txt;
    done
done