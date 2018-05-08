log_file = None
log_file_name = ""
console_debug = True

def set_log_file_name(name):
    log_file_name = name
    log_file = open(name,'a')
    
def debug(*args):
    if console_debug:
        print(*args)
    if log_file is not None:
        log_file.write(*args)
        log_file.write('\n')
