from datetime import datetime
import lxml.etree as et
from numpy import shape as np_shape
from numpy import zeros as np_zeros
from vtk.util import numpy_support

from pzero.entities_factory import TriSurf


def vtk2lxml(self,out_dir_name=None):
    
    namespace = {'xsi':"http://www.w3.org/2001/XMLSchema"}

    date = datetime.now()

    landxml =  et.Element('LandXML',
                        xmlns="http://www.landxml.org/schema/LandXML-1.2",
                        nsmap=namespace,
                        language='English',
                        readOnly='false',
                        time=date.strftime('%H:%M:%S'),
                        date=date.strftime('%Y-%m-%d'),
                        version='1.2')
    units = et.SubElement(landxml,'Units')

    metric = et.SubElement(units,'Metric',
                        areaUnit='squareMeter',
                        linearUnit='meter',
                        volumeUnit='cubicMeter',
                        temperatureUnit='celsius',
                        pressureUnit='milliBars')
    
    surfaces = et.SubElement(landxml,'Surfaces') # all of the different surfaces are grouped here

    for uid in self.geol_coll.df['uid']:

        obj = self.geol_coll.get_uid_vtk_obj(uid)

        if isinstance(obj, TriSurf):
            clean_obj = TriSurf()
            clean_obj.ShallowCopy(obj.clean_topology())
            parts = clean_obj.split_parts()
            for i, part in enumerate(parts):
                n_cells = part.GetNumberOfCells()

                cell_shape = np_shape(numpy_support.vtk_to_numpy(part.GetCell(0).GetPoints().GetData()))
                point_arr = np_zeros((n_cells,cell_shape[0],cell_shape[1]))


                if cell_shape[0] == 3:
                    surf_type = 'TIN'
                else:
                    surf_type = 'grid'
                
                surface = et.SubElement(surfaces,'Surface',name=f'{uid}_part{i}') # we can define the single surface
                source_data = et.SubElement(surface,'SourceData')
                definition = et.SubElement(surface,'Definition',surfType=surf_type) # for each surface we must define the type
                pnts = et.SubElement(definition,'Pnts') # each surface is composed by a "points" (Pnts) element
                faces = et.SubElement(definition,'Faces') # and faces
                for c_id in range(n_cells):
                    p_data = numpy_support.vtk_to_numpy(part.GetCell(c_id).GetPoints().GetData())
                    point_arr[c_id] = p_data
                id = 1

                point_dict = {}
                
                # print(point_arr[1,:])

                for c_id in range(n_cells):
                    p_data = point_arr[c_id]
                    point_id_list = []
                    # point_arr[c_id] = p_data
                    
                    for p in p_data:
                        tp = tuple(p)
                        if tp in point_dict: #if xyz are the same
                            # print(f'{point_dict[tp]} already in dict')
                            point_id_list.append(point_dict[tp])
                        
                        else:
                            point_dict[tp] = id
                            point_id_list.append(id)
                            # yxz = f'{np.around(p[0],decimals=6)+np.random.randn()/100} {np.around(p[1],decimals=6)+np.random.randn()/100} {p[2]}'

                            xyz = f'{p[0]} {p[1]} {p[2]}'
                            pnt = et.SubElement(pnts,'P',id=str(id))
                            pnt.text = xyz
                            
                            id+=1
                        
                        
                    # conn_list.append(point_id_list)

                    face = et.SubElement(faces,'F')
                    face.text = f'{point_id_list[0]} {point_id_list[1]} {point_id_list[2]}'

    tree = et.ElementTree(landxml)

    tree.write(f'{out_dir_name}/out.xml',pretty_print=True, xml_declaration=True, encoding="iso-8859-1")



def lxml2vtk(self,input_path=None):
    ...