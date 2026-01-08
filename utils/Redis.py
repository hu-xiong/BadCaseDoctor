import redis

import config


class Redis:
    def __init__(self, host, port, username=None, password=None):
        configs = config.Config()
        self.host = configs.REDIS_HOST
        self.port = configs.REDIS_PORT
        self.password = configs.REDIS_PASSWORD
        self.username = configs.REDIS_USERNAME


        self.client = (
            redis.Redis(host=self.host,
                        port=self.port,
                        username=self.username,
                        password=self.password))
    def get(self,key:str):
        return self.client.get(key)
    def set(self,key:str,value:str):
        return self.client.set(key,value)
    def delete(self,key:str):
        return self.client.delete(key)

    def hgetall(self,key:str):
        return self.client.hgetall(key)

    def hset(self,key:str,field:str,value:str):
        return self.client.hset(key,field,value)

    def hdel(self,key:str,field:str):
        return self.client.hdel(key,field)

    def lpush(self,key:str,value:str):
        return self.client.lpush(key,value)

    def lrange(self,key:str,start:int,stop:int):
        return self.client.lrange(key,start,stop)

    def lpop(self,key:str):
        return self.client.lpop(key)

    def lrem(self,key:str,count:int,value:str):
        return self.client.lrem(key,count,value)

    def ltrim(self,key:str,start:int,stop:int):
        return self.client.ltrim(key,start,stop)

    def lindex(self,key:str,index:int):
        return self.client.lindex(key,index)

    def linsert(self,key:str,where:str,pivot:str,value:str):
        return self.client.linsert(key,where,pivot,value)

    def lset(self,key:str,index:int,value:str):
        return self.client.lset(key,index,value)
    def lrange(self,key:str,start:int,stop:int):
        return self.client.lrange(key,start,stop)
    def lrange(self,key:str,start:int,stop:int):
        return self.client.lrange(key,start,stop)