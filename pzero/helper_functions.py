
def auto_sep(filename):
    from csv import Sniffer
    with open(filename,'r') as IN:
        separator = Sniffer().sniff(IN.readline()).delimiter
    return separator

def profiler(path,iter):

    '''[Gabriele] Function used to profile the time needed to run a given function. The output is a .csv file in which each row corresponds the mean run time and std of functions. As a secondary output the profiler saves the raw differences in a separate file. This tool can be used as a decorator.
    -------------------------------------------------------------
    Input:
        + path: Where to save the output files
        + iter: Number of iterations
    Output:
        + mean +- std time .csv file
        + raw data .csv file
    -------------------------------------------------------------
    Usage
    @profiler(path/to/output/file,100)
    def func(foo):
        dostuff

    '''
    import datetime
    import os
    import pandas as pd
    import numpy as np
    root,base = os.path.split(path)
    diff_list = []
    def secondary(func):
        def inner(*args,**kwargs):
            title = func.__name__
            date = datetime.datetime.now()
            print(f'\n-------------------{title} PROFILING STARTED-------------------\n')
            for i in range(iter):
                print(f'{i+1} cycle of {iter}')
                start = datetime.datetime.now()
                res = func(*args,**kwargs)
                end = datetime.datetime.now()
                diff = (end-start).total_seconds()
                diff_list.append(diff)
                print(f'cycle {i+1} completed. It took {diff} seconds')
            raw_time_diff = pd.DataFrame(diff_list,columns=['time diff [s]'])
            raw_time_diff.to_csv(os.path.join(root,f'{title}_raw{date.strftime("%d_%m_%Y-%H%M%S")}.csv'),sep=';',mode='w')
            mean = np.mean(diff_list)
            std = np.std(diff_list)

            if os.path.exists(path):
                with open(path,'a') as f:
                    f.write(f'{date.strftime("%d_%m_%Y-%H%M%S")};{title};{mean};{std};{iter};\n')
            else:
                with open(path,'a') as f:
                    f.write(f'Rec. time;function title [-];mean [s];std [-];n of iterations[-];\n')
                    f.write(f'{date.strftime("%d_%m_%Y-%H%M%S")};{title};{mean};{std};{iter};\n')
            print(f'Profiling finished in ~{mean*iter}s! The results are saved in the specified {root} directory')
            print(f'\n-------------------{title} PROFILING ENDED-------------------\n')
            return res
        return inner
    return secondary
