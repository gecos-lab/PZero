
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



def angle_wrapper(angle):
    from numpy import pi

    return angle%(2*pi)

def add_vtk_obj(self,vtk_obj,type):
    from copy import deepcopy
    from uuid import uuid4
    from .geological_collection import GeologicalCollection
    import numpy as np

    if type == 'measurement':
        curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)
        properties_name = vtk_obj.point_data_keys
        properties_components = [vtk_obj.get_point_data_shape(i)[1] for i in properties_name]
        name = f"{int(vtk_obj.get_point_data('dir'))}/{int(vtk_obj.get_point_data('dip'))}"
        curr_obj_dict['uid'] = str(uuid4())
        curr_obj_dict['name'] = name
        curr_obj_dict['topological_type'] = "VertexSet"
        curr_obj_dict['properties_names'] = properties_name
        curr_obj_dict['properties_components'] = properties_components
        curr_obj_dict['vtk_obj'] = vtk_obj
        """Add to entity collection."""
        self.parent.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
