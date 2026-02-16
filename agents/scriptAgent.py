from typing import Dict, Union
from langchain_core.language_models import BaseLLM


class scriptAgengt:
    name = "script"
    def __init__(self):
        print("初始化scriptAgent")

    def handle(self, userId: str,action:str,llm_intent: str,llm: BaseLLM,llm_script:str,info:dict) -> Dict[str, Union[int, str]]:
        print("处理scriptAgent")
        user_input = llm.splitTask(llm_script, info)
        intput=""
        num=0
        script=""
        for input in user_input:
            num=num+1
            subScript=llm.generateScript(input.get("info"),info)
            print("subScript:",subScript.get("script"))
            script=script+"script第"+str(num)+"片段："+subScript.get("script","")
        return llm.dealScript(user_input=script, info=info)











