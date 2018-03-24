import openlcb_cmri_cfg as cmri
import socket

#connection to the gateway
gateway_ip = "127.0.0.1"
gateway_port = 50010
s =socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.connect((gateway_ip,gateway_port))
print("connected to gateway!")

while True:
    buf=s.recv(200) #byte array: the raw cmri message    
    print("raw message=",buf)
    msg = cmri.CMRI_message.from_raw_message(buf)
    print("address=",msg.address)
    if msg.type_m == cmri.CMRI_message.POLL_M:
        #ask an answer to the user
        inputs_state=input("binary state of the inputs?")
        inputs=int(inputs_state,2)
        msg.type_m = cmri.CMRI_message.RECEIVE_M
        msg.message = b"\x01"+bytes((inputs,))
        s.send(msg.to_raw_message())
    elif msg.type_m==cmri.CMRI_message.TRANSMIT_M:
        for b in msg.message:
            print("output set to ",b,end=" ")
        print()
    
