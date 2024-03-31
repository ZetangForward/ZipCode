import os
import sys
current_file_path = os.path.abspath(__file__)
current_file_dir = os.path.dirname(current_file_path)
sys.path.append(current_file_dir)

from model_config import ModelConfig
from optimizer_config import OptimizerConfig
from platform_config import PlatformConfig
from task_config import TaskConfig


def merge_configs(default, custom):
    final_config = default.copy()
    for key, value in custom.items():
        if isinstance(value, dict):
            node = final_config.setdefault(key, {})
            final_config[key] = merge_configs(node, value)
        else:
            final_config[key] = value
    return final_config


def merge_dotdicts(d1, d2):
    merged = d1.copy()  # 做一个d1的浅拷贝
    for k, v in d2.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            # 如果两个DotDict都有相同的key，并且对应的value也是字典，递归合并
            merged[k] = merge_dotdicts(DotDict(merged[k]), v)
        else:
            # 如果不存在冲突或者其中一个value不是字典，直接更新值
            merged[k] = v
    return DotDict(merged)


class DotDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    def __init__(self, dct):
        for key, value in dct.items():
            if hasattr(value, 'keys'):
                value = DotDict(value)
            self[key] = value

    def __repr__(self):
        def recursive_repr(dct, level=0):
            indent = '  ' * level
            lines = []
            for key, value in dct.items():
                if isinstance(value, DotDict):
                    lines.append(f"{indent}{key}:")
                    lines.extend(recursive_repr(value, level + 1))
                else:
                    lines.append(f"{indent}{key}: {value}")
            return lines
        
        str_lines = recursive_repr(self)
        return '\n'.join(str_lines)


class WrapConfigs:

    def __init__(
            self, 
            model_name_or_path, 
            model_configs,
            opt_name,
            opt_configs, 
            platform_name, 
            data_name,
            task_configs,
        ) -> None:
        self.model_name_or_path = model_name_or_path
        self.model_configs = model_configs
        self.opt_name = opt_name
        self.opt_configs = opt_configs
        self.platform_name = platform_name
        self.data_name = data_name
        self.task_configs = task_configs
        self.all_configs = self.set_all_configs()

    def set_all_configs(self):
        model_config = ModelConfig(self.model_name_or_path, **self.model_configs)
        optimizer_config = OptimizerConfig(self.opt_name, **self.opt_configs)
        platform_config = PlatformConfig(self.platform_name)
        task_config = TaskConfig(self.data_name, **self.task_configs)

        default_config = {
            "model": model_config.cfg,
            "optimizer": optimizer_config.cfg,
            "platform": platform_config.cfg,
            "task": task_config.cfg,
        }

        return DotDict(default_config)
