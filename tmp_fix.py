            print(f"[REACT-STREAM] 生成的 Todos: {todos}")
            
            # ✨ 使用文心 4.5 Turbo 整理思考过程（隐藏原始混乱的 thinking_content）
            if reasoning and isinstance(reasoning, str) and reasoning.strip():
                try:
                    from llm.qianfan_llm import QianfanLLM
                    summary_llm = QianfanLLM(model='ernie-4.5-turbo-128k')
                    
                    summary_prompt = f"""你是一个助手，需要将 AI 的内部思考过程整理成用户能看懂的简洁说明。

【原始思考内容】
{reasoning[:600]}

【任务】
将以上思考过程整理为 1-2 句通顺的中文，告诉用户你接下来要做什么。

【要求】
1. 纯中文，不要出现工具名（grep、modify 等）
2. 1-2 句话，简洁明了
3. 例如：「我先搜索登录相关的 Bug，然后修改它们的状态为关闭。」
4. 不要出现参数名、ID 等技术细节

【整理后的说明】"""
                    
                    cleaned_reasoning = await summary_llm.chat(summary_prompt)
                    if cleaned_reasoning:
                        print(f"[REACT] ✨ 整理后的思考：{cleaned_reasoning[:100]}...")
                        # 用整理后的文本替换原始的 reasoning，实时下发
                        yield {'event': 'reasoning', 'content': cleaned_reasoning}
                    else:
                        print("[REACT] 整理思考失败，不展示思考过程")
                except Exception as e:
                    print(f"[REACT] 整理思考过程失败：{e}")
            
            if not todos:
