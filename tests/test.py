#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：调用百度AI对话接口
"""

import requests
import json
from urllib3.exceptions import InsecureRequestWarning

# 禁用SSL警告
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

def call_dialog_api():
    """调用对话API接口"""
    
    # API端点
    url = 'https://njjs-its-aitpm04.njjs.baidu.com:8590/dialog/api/v1/dialog/message'
    
    # 请求头
    headers = {
        'Accept': 'text/event-stream, text/event-stream',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Authorization': 'Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbkNyZWF0ZVRpbWUiOjE3NTUyNDE1NzE3NTAsIlgtdHJhZmZpYy1Vc2VySWQiOjE3NTk2MzkyNjUzODk3LCJ1c2VyX25hbWUiOiLkuIDkuKrkurrlnKjmtYHmtao5Iiwic2NvcGUiOlsiYWxsIl0sIm5pY2tuYW1lIjoi6IOh6ZuEIiwiZXhwIjoxNzYzMDE3NTcxLCJqdGkiOiIxMmE3NjRhMy1mZTMyLTRhYTYtYjE0ZS0yN2M5Yjc4ZTczMzMiLCJjbGllbnRfaWQiOiJmcm9udGVuZCJ9.BciP-EG_ekqLIRg_z4-PLrTXRQxRaOYn2RWkuyiWextEGTnVUqFYz10hdRdp9DfFR1Xpd6aHWGJDJdTn0Ep459RQJkvVoxluidNK24qwBSCV_WQsyDJ7VBFsx-kuo-ed_1uwkPMwY3LLA4dTgnPq1aI8C3qX0h8i2vdDjpjTY2n8J6Zprh_Jfb6KMtTMiSxGh5pjo8VXdR4lAPtJOUFuPTNVuJNYBVWRTZKHn_YgBVaeiJWlTp-UbHTWIApSKqwBA7DO6vDc6wqKRRPFJVOleNPxrDwT-SguzLEKSom1LkAyN7HRwLULqcbWB1uL37USn4Q4uBRKV4SpqVkKMSKrsA',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://njjs-its-aitpm04.njjs.baidu.com:8590',
        'Referer': 'https://njjs-its-aitpm04.njjs.baidu.com:8590/web-saas/professional-qna/app?batchId=8097f86e-35cd-4c9b-adfd-3b031c9d5716',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        'reallyGroupId': '51',
        'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"'
    }
    
    # Cookie字符串
    cookies_str = 'BAIDUID=A624CAD0FFF6E609AEA0B40962D52FEA:FG=1; UUAP_TRACE_TOKEN=0f0f3c1e4bac5a829da4bc89711c8cd3; H_WISE_SIDS_BFESS=60278_61027_61162_61246_60853_61351_61358_61371_61390_61392_61427_61433_61429_61509_61525; BIDUPSID=A624CAD0FFF6E609AEA0B40962D52FEA; PSTM=1743484861; BAIDUID_BFESS=A624CAD0FFF6E609AEA0B40962D52FEA:FG=1; jsdk-uuid=d4327fd0-3eaf-4559-bdb6-dc9ee304ab9a; __bid_n=196760a1d0c80481ae161e; BDUSS=mlWNjFPSnNxUGhLTWJNRFJIckVnUnFhdmZiZFItc3dGS2RLazV0ZlZZWW96M0ZvRVFBQUFBJCQAAAAAAAAAAAEAAADzMIl~0ru49sjL1NrB98DLOQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAChCSmgoQkpoN; BDUSS_BFESS=mlWNjFPSnNxUGhLTWJNRFJIckVnUnFhdmZiZFItc3dGS2RLazV0ZlZZWW96M0ZvRVFBQUFBJCQAAAAAAAAAAAEAAADzMIl~0ru49sjL1NrB98DLOQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAChCSmgoQkpoN; ZFY=kpO0or:AcfpmgmwR03Ko63:BpLg2DBEYlFqNsBApLHO9Y:C; H_PS_PSSID=60278_62325_63143_63274_63805_63881_63948_63995_64009_64015_64026_64019_64057_64085_64139_64146_64156_64173; H_WISE_SIDS=60278_62325_63143_63274_63805_63881_63948_63995_64009_64015_64026_64057_64085_64139_64146_64156_64173; jsdk-user=UhS/a2XJOXsWwlz7TwOmBQ==; SECURE_ZT_EXTRA_INFO=-2WOclZDy2e-tvfKIQjxeqKWNpxX2J_UO2vLAbpC22ALGDMFyQb2Er_tpGdHEtUaHzmRZ_Ao0cM45OuowAWZ4KLbIp1QBhfa9kgePf35AL8; ZT_EXTRA_INFO=-2WOclZDy2e-tvfKIQjxeqKWNpxX2J_UO2vLAbpC22ALGDMFyQb2Er_tpGdHEtUaHzmRZ_Ao0cM45OuowAWZ4KLbIp1QBhfa9kgePf35AL8; UUAP_P_TOKEN=PT-1155192135485157377-d245d5964eef528710a0ea7f1a51aa49a59e071642f99e8fe5c98f6cdde66ba6-uuapenc; SECURE_UUAP_P_TOKEN=PT-1155192135485157377-WCYm7YRIrm0Hh227DVud-uuap; ab_sr=1.0.1_YjM4M2FmZDc3YTAzZWZhMzA1ZDZjNzBiYTczZDJlMzYxM2QyOWZmNDkxNWM5ZDRjOTlmZGJmN2RiMDQ5OWNiZDc4ZTFjZTJmZGUyYjI0NzA3NTc2NDEwYzUyYzQ3NGEzZDNiMDMzMjhmYmE5MTBjMzg2OTJiZGFkMTcxNDg4ZmM3MTM1NmUyMmIwYThlM2I2ZDZmNjBkYzk4OWRlY2QyYTQzM2FjZDE1NDRjMTM0ZWE4NDczNGMxZmRkMTNkZGMx; RT="z=1&dm=baidu.com&si=83158365-1307-47a2-b099-aa1cec603cf8&ss=mechicar&sl=4&tt=5fc&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf&ld=1i723"'
    
    # 将cookie字符串转换为字典
    cookies = {}
    for cookie in cookies_str.split('; '):
        if '=' in cookie:
            name, value = cookie.split('=', 1)
            cookies[name] = value
    
    # 请求数据
    data = {
        "type": "IM_CLICK",
        "data": {
            "queryId": "92130233-0e42-4486-8ece-76d22e8c8543",
            "parentQueryId": "-",
            "childrenQueryIds": [],
            "batchId": "8097f86e-35cd-4c9b-adfd-3b031c9d5716",
            "queryText": "西安最新限行政策是什么？",
            "params": {
                "scene_id": 233,
                "modelType": "deepSeekV3Stream",
                "supportDeepSearch": False,
                "modelName": "DeepSeek-V3",
                "isAgent": False,
                "supportWebSearch": False
            },
            "sceneCode": "professional-qna",
            "intentionCode": "saas_qa_stream_cot_version",
            "requestTime": "2025-08-15 15:51:27",
            "answer": "",
            "data": {},
            "cot": [],
            "status": "100",
            "satisfyState": 0,
            "recommend": [],
            "introduce": "",
            "intentionConfirm": [],
            "isNewReGen": False
        }
    }
    
    try:
        print("正在调用API接口...")
        print(f"URL: {url}")
        print(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # 发送POST请求
        response = requests.post(
            url=url,
            headers=headers,
            cookies=cookies,
            json=data,
            verify=False,  # 对应curl的--insecure参数
            timeout=30
        )
        
        print(f"\n响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        
        # 检查响应内容类型
        if 'text/event-stream' in response.headers.get('content-type', ''):
            print("\n响应内容 (Server-Sent Events):")
            for line in response.text.split('\n'):
                if line.strip():
                    print(f"  {line}")
        else:
            print(f"\n响应内容: {response.text}")
            
        return response
        
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None
    except Exception as e:
        print(f"发生错误: {e}")
        return None

def main():
    """主函数"""
    print("=" * 50)
    print("百度AI对话接口测试脚本")
    print("=" * 50)
    
    # 调用API
    response = call_dialog_api()
    
    if response:
        print("\n" + "=" * 50)
        print("测试完成")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("测试失败")
        print("=" * 50)

if __name__ == "__main__":
    main()
