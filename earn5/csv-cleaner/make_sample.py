# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

out = Path(__file__).with_name("样例_脏数据.csv")
df = pd.DataFrame(
    {
        "姓名": [" 张三 ", "李四", "张三", None, "王五"],
        "下单日期": ["2024/1/2", "2024-01-03", "2024/1/2", "", "01/05/2024"],
        "金额": [12.5, 8, 12.5, None, 20],
        "备注": ["  正常 ", "正常", "  正常 ", None, "加急"],
    }
)
df.to_csv(out, index=False, encoding="utf-8-sig")
print(out)
