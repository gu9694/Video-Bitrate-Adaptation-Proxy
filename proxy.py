#!/usr/bin/env python
import sys
import socket
import thread
import select
import time
import re
from socket import socket, AF_INET, SOCK_STREAM


# several parameters
MAXPENDING=100 # for socket listening
bufferSize=4096 # buffer size of socket to send and receive request. To save memmory, 4096 is enough.
receive_bufferSize=524288 # buffer size of socket to receive message, it should be large enough to receive the manifest file

class qiaoyu:
    def __init__(self,myproxy,alpha,fake_ip,web_server_ip,log_record):
        self.clientSocket,addr=myproxy.accept() # initialize socket between proxy and client
        print ("Client socket is configured successfully")

        self.alpha=alpha # alpha
        self.fake_ip=fake_ip # faki ip
        self.web_server_ip=web_server_ip # web server ip

        self.real_time_bitrate=10 # real time bitrate, update every time
        self.average_throughout=0 # average throughput. current EWMA
        self.current_length=0; # record the length of each chunk
        self.blank_chunk=0; # to judge whether current chunk contains bitrate info, 1 is blank, 0 is no-blank


        self.bitrate_to_be_chosen=[] # a list of bitrate to be chosen, obtained from manifest file
        self.buffer_size=bufferSize # buffer size of send request 
        self.receiver_buffer=receive_bufferSize # buffer size of receive manifest file

        self.serverSocket=socket(AF_INET,SOCK_STREAM) # initialize socket between socket and server
        self.serverSocket.bind((self.fake_ip,0))
        self.serverSocket.connect((self.web_server_ip,8080))
        print("ServerSocket is configured successfully")

        self.log_record=log_record

    def choose_bitrate(self,rtb,bitrate):   
        max_b=rtb/1.5
        bitrate.sort()
        if bitrate[0]>= max_b:
            return bitrate[0]
        for i in range(len(bitrate)):
            if bitrate[i]>= max_b:
                return bitrate[i-1]
        return max(bitrate)


    def connect(self):     
        inputs=[self.clientSocket,self.serverSocket]
        outputs=[]
        ts=time.time()

        while True:

            readable, writable, exceptional = select.select(inputs, outputs, inputs) # proxy outbound should wait before it's ready to read

            for i in readable: # judge which socket is used now
                message=i.recv(4096) # receive message in socket
                if message:
                    if i is self.clientSocket: # if the message is received by socket between client and proxy
                        # we should check two items : 1. whether current request has '.f4m'
                        #                             2. whether current request has real time bitrate info



                        # check 1: 1. whether current request has '.f4m'                        
                        judge_f4m=re.search(re.compile(r'big_buck_bunny.f4m'),message) # the message is sent from client to proxy to server

                        # situation 1: no .f4m request, usually it is http get request
                        #             in this situation, we should directly send the request from proxy to server
                        if judge_f4m is None:
                            message.decode()
                            print("Current HTTP 1.1 GET request is:")
                            print(message)
                            message.encode()
                        
                        # situtation 2: contain .f4m request 
                        #               in this situation, we should replace .f4m to _nolist
                        if judge_f4m != None:
                            # step 1: replace .f4m with _nolist.f4m
                            message.decode()
                            print("Current .f4m request is: ")
                            print (message)
                            raw_message=message
                            message=message.replace('big_buck_bunny.f4m','big_buck_bunny_nolist.f4m')
                            print(".f4m is modified successfully")
                            raw_message.encode()
                            message.encode()
                            message_processed = message 
                            message_raw = raw_message
                            
                            # step 2: fetch manifest file from server
                            self.serverSocket.send(raw_message)  # notice that proxy should fetech .f4m for itself!!!!
                            mainifest_file=self.serverSocket.recv(receive_bufferSize)
                            print("Manifest file has been fetched successfully...")

                            # step 3: obtain all bitrates to be chosen
                            bitrate_part=re.findall(re.compile(r'bitrate="[0-9]*"'),mainifest_file)
                            for i in bitrate_part:
                                tmp=i.split('"')[1]
                                tmp_int=int(tmp)
                                self. bitrate_to_be_chosen.append(tmp_int)
                            print ("The list of bitrates to be chosen is ")

                            for i in self.bitrate_to_be_chosen:
                                print (i,'bps')


                        # check 2: whether current request contains real time biterate info
                        judge_real_time=re.search(re.compile(r'/vod/.*Frag[0-9]*'),message)

                        # situation 1: no bitrate info, just ignore this fragment of data
                        if judge_real_time is None:
                            print("Current id doesn't contain data, so ignore it...")
                            self.blank_chunk=1;       

                        # situation 2: contain bitrate info
                        #              we should replace throughput with real-time throughput                
                        if judge_real_time != None:
                            real_time_bit_rate_str=str(self.real_time_bitrate)                            
                            log_id=re.sub(r'/vod/[0-9]*','/vod/'+real_time_bit_rate_str,judge_real_time.group(0))
                            message=re.sub(re.compile(r'/vod/[0-9]*'),'/vod/'+real_time_bit_rate_str,message)
                            self.blank_chunk=0;


                        # after finishing two checkings, we should send request to server
                        self.serverSocket.send(message)
                        print("A new round begins...")

                    if i is self.serverSocket: # if the message is received by socket between client and proxy
                        judge_length=re.search(re.compile(r'Content-Length: .\w+'),message,flags=0)

                        if judge_length != None: # obtain the length of current chunk
                            self.current_length=float(judge_length.group(0)[16:]) # obtian the number
                            print("Current length is ",self.current_length)                          
                            buffer_num=1 
                        else:
                            buffer_num=buffer_num+1 # calculate num of buffer needed to save current chunk
                        self.clientSocket.send(message)
                        if buffer_num*4096>self.current_length: # if storage is large enough to receive the message, then begin to preocess current chunk
                            print("Number of buffers needed to save current chunk length:", buffer_num)

                            tf=time.time() # tf
                            duration=1*(tf-ts) # duration
                            print("Current duration is:",duration)
                            throughout=8*self.current_length/duration/1024 # throughput
                            print("Current throghput is:",throughout)
                            self.average_throughout=self.alpha*throughout+(1-self.alpha)*self.average_throughout # EWMA
                            ts=time.time()
                            print("Current average throughput (EWMA) is: ",self.average_throughout)
                            buffer_num=1
                            if self.blank_chunk==0:                                  
                                self.log_record.write('%d %.3f %d %.1f %d %s %s\n'%(tf,duration,throughout,self.average_throughout,self.real_time_bitrate,self.web_server_ip,log_id))
                                print("Current chosen bitrate is:",self.real_time_bitrate)
                                self.real_time_bitrate=self.choose_bitrate(self.average_throughout,self.bitrate_to_be_chosen) # choose proper bitrate
                                   
                #else:
                    #break
        self.clientSocket.close()
        self.serverSocket.close()
        self.log_record.close()


if __name__ == '__main__':
    #set up command line inputs
    log=sys.argv[1]
    alpha=sys.argv[2]
    listen_port=sys.argv[3]
    fake_ip=sys.argv[4]
    web_server_ip=sys.argv[5]

    #str to int,float
    listen_port_int=int(listen_port)
    alpha=float(alpha)

    #initialize server socket
    myproxy=socket(AF_INET,SOCK_STREAM)
    myproxy.bind(('', listen_port_int))
    myproxy.listen(MAXPENDING)
    print ('My proxy is set up successfully...')
    print ('Listen port is:')
    print (listen_port_int)
    log_record=open(log,'w')
    while True:       
        thread.start_new_thread(qiaoyu(myproxy,alpha,fake_ip,web_server_ip,log_record).connect,())
        print ("The log file is ready to record proxy activities...")


