"""gocad2vtk.py
PZero© Andrea Bistacchi"""

from copy import deepcopy
from numpy import column_stack as np_column_stack
from numpy import shape as np_shape
from vtk import vtkPoints, vtkCellArray, vtkDataArrayCollection, vtkFloatArray, vtkLine, vtkTriangle, vtkVertex 
import uuid
from .entities_factory import VertexSet, PolyLine, TriSurf, XsVertexSet, XsPolyLine
from pzero.collections.geological_collection import GeologicalCollection
from pzero.collections.boundary_collection import BoundaryCollection
from .helper_dialogs import input_text_dialog, input_combo_dialog, options_dialog

"""We import only come Gocad object attributes.
Other Gocad ASCII properties/fields/keys not implemented in PZero are:
    CRS-related -> we use a single homogeneous CRS in every
    project and conversions must be performed before importing data.
    'CRS_name'
    'CRS_projection'
    'CRS_datum'
    'CRS_axis_name'
    'CRS_axis_unit'
    'CRS_z_positive'
    STRATIGRAPHIC_POSITION -> this in Gocad includes geological age (string) and time
    (number), but in PZero these are defined in the legend for each geological feature. 
    Properties -> some of these can be retrieved from properties stored in VTK
    arrays, and for units the same as for CRS applies (generally we use SI units).
    'properties_no_data_values'
    'properties_components_sum': int(0),
    'properties_units': []
    Properties-related keywords, probably redundant.
     'PROP_LEGAL_RANGES'
     'PROPERTY_CLASSES'
     'PROPERTY_KINDS'
     'PROPERTY_SUBCLASSES'
     'INTERPOLATION_METHODS'
     'PROPERTY_CLASS_HEADER'
     'kind:'
     'unit:'
     'is_z:'
     Cosmetic rendering- or legend-related properties/keywords.
    '*atoms*size:'
    '*atoms*color:'
    'use_feature_color:'
    'atoms:'
    '*painted*variable:'
    '*painted:'
    '*atoms*symbol:'
    'last_selected_folder:'
    '*vectors3d*variable:'
    '*tensors3d*variable:'
    'vectors3d:'
    '*vectors3d*color:'
    '*vectors3d*arrow_size:'
    '*vectors3d*rescale:'
    '*vectors3d*mode:'
    '*vectors3d*arrow:'
     '*solid*color:'
     'mesh:'
     'parts:'
     'pclip:'
     'low_clip:'
     'high_clip:'
     'colormap:'
     When importing we do not consider the following
     keywords that could be important.
     'BSTONE'
     'BORDER'
"""


def gocad2vtk(self=None, in_file_name=None, uid_from_name=None):
    """
    Read a GOCAD ASCII file and add, to the geol_coll GeologicalCollection(), all the
    pointset, polyline, triangulated surfaces as VTK polydata entities.
    <self> is the calling ProjectWindow() instance.
    """
    """Define import options."""
    scenario_default = input_text_dialog(parent=None, title="Scenario", label="Default scenario", default_text="undef")
    if not scenario_default:
        scenario_default = "undef"
    geological_type_default = input_combo_dialog(parent=None, title="Geological type", label="Default geological type", choice_list=GeologicalCollection.valid_geological_types)
    if not geological_type_default:
        geological_type_default = "undef"
    geological_feature_from_name = options_dialog(title="Feature from name", message="Get geological feature from object name if not defined in file", yes_role="Yes", no_role="No", reject_role=None)
    if geological_feature_from_name == 0:
        geological_feature_from_name = True
    else:
        geological_feature_from_name = False
    """Open input file"""
    fin = open(in_file_name, 'rt')
    """Number of entities before importing________________________________"""
    n_entities_before = self.geol_coll.get_number_of_entities()
    """Initialize entity_counter"""
    entity_counter = 0
    """Parse fin file"""
    for line in fin:
        """Read one line from file."""
        clean_line = line.strip().split()

        """The effect of the following if/elif cascade is to loop for every single object marked by
        the GOCAD keyword, reading the lines that we want to import and skipping the others."""
        if clean_line[0] == 'GOCAD':
            """A new entity starts here in a GOCAD file, so here we create a new empty dictionary,
            then we will fill its components in the next lines. Use deepcopy otherwise the
            original dictionary would be altered."""
            curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)
            curr_obj_dict['scenario'] = scenario_default

            """Store uid and topological type of new entity."""
            curr_obj_dict['uid'] = str(uuid.uuid4())

            """Create the empty vtk object with class = topological_type."""
            if clean_line[1] == 'VSet':
                curr_obj_dict['topological_type'] = 'VertexSet'
                curr_obj_dict['vtk_obj'] = VertexSet()
                curr_obj_dict['geological_type'] = geological_type_default
            elif clean_line[1] == 'PLine':
                curr_obj_dict['topological_type'] = 'PolyLine'
                curr_obj_dict['vtk_obj'] = PolyLine()
                curr_obj_dict['geological_type'] = geological_type_default
            elif clean_line[1] == 'TSurf':
                curr_obj_dict['topological_type'] = 'TriSurf'
                curr_obj_dict['vtk_obj'] = TriSurf()
                curr_obj_dict['geological_type'] = geological_type_default
            else:
                """Here topological types different from the allowed ones are handled.
                At the moment THIS WILL CAUSE ERRORS - KEEP THIS MESSAGE JUST FOR DEBUGGING.
                This must be reimplementende in sucha way that, is non-valid objects are found,
                the file reader jumps to the next line starting with the 'GOCAD' keyword (if any)."""
                self.TextTerminal.appendPlainText("gocad2vtk - entity type not recognized ERROR.")

            """Create empty arrays for coordinates and topology and a counter for properties."""
            curr_obj_points = vtkPoints()
            curr_obj_cells = vtkCellArray()
            curr_obj_properties_collection = vtkDataArrayCollection()
            properties_number = 0

        elif 'name:' in clean_line[0]:
            if clean_line[0] == 'name:':
                """standard import"""
                curr_obj_dict['name'] = ("_".join(clean_line[1:]))  # see if a suffix must be added to split multipart
                if geological_feature_from_name:
                    curr_obj_dict['geological_feature'] = curr_obj_dict['name']
            else:
                """solves a bug in Move that does not add a space after name: """
                curr_obj_dict['name'] = ("_".join(clean_line[:]))
                curr_obj_dict['name'] = curr_obj_dict['name'][5:]  # this removes 'name:'
                if geological_feature_from_name:
                    curr_obj_dict['geological_feature'] = curr_obj_dict['name']
            if uid_from_name:
                curr_obj_dict['uid'] = curr_obj_dict['name']

        elif clean_line[0] == 'GEOLOGICAL_TYPE':
            curr_obj_dict['geological_type'] = ("_".join(clean_line[1:])).lower()
            if curr_obj_dict['geological_type'] not in GeologicalCollection.valid_geological_types:
                if "Fault" in curr_obj_dict['geological_type']:
                    curr_obj_dict['geological_type'] = "fault"
                elif "fault" in curr_obj_dict['geological_type']:
                    curr_obj_dict['geological_type'] = "fault"
                elif  "Horizon" in curr_obj_dict['geological_type']:
                    curr_obj_dict['geological_type'] = "top"
                else:
                    curr_obj_dict['geological_type'] = "undef"

        elif clean_line[0] == 'GEOLOGICAL_FEATURE':
            curr_obj_dict['geological_feature'] = ("_".join(clean_line[1:]))

        elif clean_line[0] == 'PROPERTIES':
            """Populate the list of property names, the properties number, and initialize the VTK arrays."""
            for prop in clean_line[1:]:
                curr_obj_dict['properties_names'].append(prop)
            properties_number = len(curr_obj_dict['properties_names'])
            for i in range(properties_number):
                new_prop = vtkFloatArray()
                curr_obj_properties_collection.AddItem(new_prop)
                curr_obj_properties_collection.GetItem(i).SetName(curr_obj_dict['properties_names'][i])

        elif clean_line[0] == 'ESIZES':
            ESZ_str = clean_line[1:]
            for i in range(len(ESZ_str)):
                curr_obj_dict['properties_components'].append(int(ESZ_str[i]))
                curr_obj_properties_collection.GetItem(i).SetNumberOfComponents(int(ESZ_str[i]))

        elif clean_line[0] == 'SUBVSET':  # see if and how to start a new SUBVSET part here
            pass

        elif clean_line[0] == 'ILINE':  # see if and how to start a new ILINE part here
            pass

        elif clean_line[0] == 'TFACE':  # see if and how to start a new TFACE part here
            pass

        elif clean_line[0] == 'VRTX':
            curr_obj_points.InsertPoint(int(clean_line[1]) - 1, float(clean_line[2]), float(clean_line[3]), float(clean_line[4]))  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK

        elif clean_line[0] == 'PVRTX':
            curr_obj_points.InsertPoint(int(clean_line[1]) - 1, float(clean_line[2]), float(clean_line[3]), float(clean_line[4]))  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK
            if properties_number > 0:
                """Now we set values in the properties float arrays"""
                """_____________Check if all is OK here with vector properties_________________________________________________"""
                i = 5  # i = 5 since the first five elements have already been read: PVRTX, id, X, Y, Z
                for j in range(properties_number):
                    this_prop = curr_obj_properties_collection.GetItem(j)
                    if curr_obj_dict['properties_components'][j] == 1:
                        this_prop.InsertTuple1(int(clean_line[1]) - 1,
                                               float(clean_line[i]))
                        i = i + 1
                    elif curr_obj_dict['properties_components'][j] == 2:
                        this_prop.InsertTuple2(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]))
                        i = i + 2
                    elif curr_obj_dict['properties_components'][j] == 3:
                        this_prop.InsertTuple3(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]),
                                               float(clean_line[i + 2]))
                        i = i + 3
                    elif curr_obj_dict['properties_components'][j] == 4:
                        this_prop.InsertTuple4(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]),
                                               float(clean_line[i + 2]),
                                               float(clean_line[i + 3]))
                        i = i + 4
                    elif curr_obj_dict['properties_components'][j] == 6:
                        this_prop.InsertTuple4(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]),
                                               float(clean_line[i + 2]),
                                               float(clean_line[i + 3]),
                                               float(clean_line[i + 4]),
                                               float(clean_line[i + 5]))
                        i = i + 6
                    elif curr_obj_dict['properties_components'][j] == 9:
                        this_prop.InsertTuple4(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]),
                                               float(clean_line[i + 2]),
                                               float(clean_line[i + 3]),
                                               float(clean_line[i + 4]),
                                               float(clean_line[i + 5]),
                                               float(clean_line[i + 6]),
                                               float(clean_line[i + 7]),
                                               float(clean_line[i + 8]))
                        i = i + 9
                    else:
                        """Discard property if it is not 1D, 2D, 3D, 4D, 6D or 9D"""
                        i = i + curr_obj_dict['properties_components'][j]
                        curr_obj_dict['properties_names'] = curr_obj_dict['properties_names'].remove(j)
                        properties_number = properties_number - 1
                        curr_obj_dict['properties_components'].remove(j)
                        curr_obj_properties_collection.RemoveItem(j)

        elif clean_line[0] == 'ATOM':
            """NOT YET IMPLEMENTED"""
            # atom_id = int(clean_line[1]) - 1
            # vrtx_id = int(clean_line[2]) - 1
            pass

        elif clean_line[0] == 'SEG':
            line = vtkLine()
            line.GetPointIds().SetId(0, int(clean_line[1]) - 1)  # "-1" since first vertex has index 0 in VTK
            line.GetPointIds().SetId(1, int(clean_line[2]) - 1)
            curr_obj_cells.InsertNextCell(line)

        elif clean_line[0] == 'TRGL':
            triangle = vtkTriangle()
            triangle.GetPointIds().SetId(0, int(clean_line[1]) - 1)  # "-1" since first vertex has index 0 in VTK
            triangle.GetPointIds().SetId(1, int(clean_line[2]) - 1)
            triangle.GetPointIds().SetId(2, int(clean_line[3]) - 1)
            curr_obj_cells.InsertNextCell(triangle)

        elif clean_line[0] == 'END':
            """When END reached, process the arrays and write the VTK entity with properties to the project geol_coll"""
            entity_counter += 1  # update entity counter

            """Write points and cells TO VTK OBJECT"""
            if curr_obj_dict['topological_type'] == 'VertexSet':
                self.TextTerminal.appendPlainText("Importing Gocad VSet (VertexSet) as a PolyData 0D in VTK with name: " + curr_obj_dict['name'])
                curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
                """Vertex cells, one for each point, are added here."""
                for pid in range(curr_obj_dict['vtk_obj'].GetNumberOfPoints()):
                    vertex = vtkVertex()
                    vertex.GetPointIds().SetId(0, pid)
                    curr_obj_cells.InsertNextCell(vertex)
                curr_obj_dict['vtk_obj'].SetVerts(curr_obj_cells)

            elif curr_obj_dict['topological_type'] == 'PolyLine':
                self.TextTerminal.appendPlainText("Importing GOCAD PLine (PolyLine) as a PolyData 1D in VTK with name: " + curr_obj_dict['name'])
                curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
                curr_obj_dict['vtk_obj'].SetLines(curr_obj_cells)

            elif curr_obj_dict['topological_type'] == 'TriSurf':
                self.TextTerminal.appendPlainText("Importing GOCAD TSurf (TriSurf) as a PolyData 2D in VTK with name: " + curr_obj_dict['name'])
                curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
                curr_obj_dict['vtk_obj'].SetPolys(curr_obj_cells)

            if properties_number > 0:
                for i in range(properties_number):
                    curr_obj_dict['vtk_obj'].GetPointData().AddArray(curr_obj_properties_collection.GetItem(i))

            print( curr_obj_dict['vtk_obj'])

            """Add current_entity to entities collection"""
            self.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
            del curr_obj_points
            del curr_obj_cells
            del curr_obj_properties_collection
            del curr_obj_dict

            """Closing message"""
            self.TextTerminal.appendPlainText("Object n. " + str(entity_counter) + " saved")

    n_entities_after = self.geol_coll.get_number_of_entities()
    self.TextTerminal.appendPlainText("Entities before importing: " + str(n_entities_before))
    self.TextTerminal.appendPlainText("Entities after importing: " + str(n_entities_after))
    self.TextTerminal.appendPlainText("Entities imported: " + str(entity_counter))


def gocad2vtk_section(self=None, in_file_name=None, uid_from_name=None, x_section=None):
    """
    Read a GOCAD ASCII file and add, to the geol_coll GeologicalCollection(), all the
    pointset, polyline, triangulated surfaces as VTK polydata entities.
    This is the specific implementation for objects belonging to a cross section.
    <self> is the calling ProjectWindow() instance.
    """
    """Define import options."""
    scenario_default = input_text_dialog(parent=None, title="Scenario", label="Default scenario", default_text="undef")
    if not scenario_default:
        scenario_default = "undef"
    geological_type_default = input_combo_dialog(parent=None, title="Geological type", label="Default geological type", choice_list=GeologicalCollection.valid_geological_types)
    if not geological_type_default:
        geological_type_default = "undef"
    geological_feature_from_name = options_dialog(title="Feature from name", message="Get geological feature from object name if not defined in file", yes_role="Yes", no_role="No", reject_role=None)
    if geological_feature_from_name == 0:
        geological_feature_from_name = True
    else:
        geological_feature_from_name = False
    """Open input file"""
    fin = open(in_file_name, 'rt')
    """Number of entities before importing________________________________"""
    n_entities_before = self.geol_coll.get_number_of_entities()
    """Initialize entity_counter"""
    entity_counter = 0
    """Parse fin file"""
    for line in fin:
        """Read one line from file."""
        clean_line = line.strip().split()

        """The effect of the following if/elif cascade is to loop for every single object marked by
        the GOCAD keyword, reading the lines that we want to import and skipping the others."""
        if clean_line[0] == 'GOCAD':
            """A new entity starts here in a GOCAD file, so here we create a new empty dictionary,
            then we will fill its components in the next lines. Use deepcopy otherwise the
            original dictionary would be altered."""
            curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)
            curr_obj_dict['x_section'] = x_section
            curr_obj_dict['scenario'] = scenario_default

            """Store uid and topological type of new entity."""
            curr_obj_dict['uid'] = str(uuid.uuid4())

            """Create the empty vtk object with class = topological_type."""
            if clean_line[1] == 'VSet':
                curr_obj_dict['vtk_obj'] = XsVertexSet(x_section_uid=x_section, parent=self)
                curr_obj_dict['topological_type'] = 'XsVertexSet'
                curr_obj_dict['geological_type'] = geological_type_default
            elif clean_line[1] == 'PLine':
                curr_obj_dict['vtk_obj'] = XsPolyLine(x_section_uid=x_section, parent=self)
                curr_obj_dict['topological_type'] = 'XsPolyLine'
                curr_obj_dict['geological_type'] = geological_type_default
            else:
                """Here topological types different from the allowed ones are handled.
                At the moment THIS WILL CAUSE ERRORS - KEEP THIS MESSAGE JUST FOR DEBUGGING.
                This must be reimplementende in sucha way that, is non-valid objects are found,
                the file reader jumps to the next line starting with the 'GOCAD' keyword (if any)."""
                self.TextTerminal.appendPlainText("gocad2vtk - entity type not recognized ERROR.")

            """Create empty arrays for coordinates and topology and a counter for properties."""
            curr_obj_points = vtkPoints()
            curr_obj_cells = vtkCellArray()
            curr_obj_properties_collection = vtkDataArrayCollection()
            properties_number = 0

        elif 'name:' in clean_line[0]:
            if clean_line[0] == 'name:':
                """standard import"""
                curr_obj_dict['name'] = ("_".join(clean_line[1:]))  # see if a suffix must be added to split multipart
                if geological_feature_from_name:
                    curr_obj_dict['geological_feature'] = curr_obj_dict['name']
            else:
                """solves a bug in Move that does not add a space after name: """
                curr_obj_dict['name'] = ("_".join(clean_line[:]))
                curr_obj_dict['name'] = curr_obj_dict['name'][5:]  # this removes 'name:'
                if geological_feature_from_name:
                    curr_obj_dict['geological_feature'] = curr_obj_dict['name']
            if uid_from_name:
                curr_obj_dict['uid'] = curr_obj_dict['name']

        elif clean_line[0] == 'GEOLOGICAL_TYPE':
            curr_obj_dict['geological_type'] = ("_".join(clean_line[1:])).lower()
            if curr_obj_dict['geological_type'] not in GeologicalCollection.valid_geological_types:
                if "Fault" in curr_obj_dict['geological_type']:
                    curr_obj_dict['geological_type'] = "fault"
                elif "fault" in curr_obj_dict['geological_type']:
                    curr_obj_dict['geological_type'] = "fault"
                elif  "Horizon" in curr_obj_dict['geological_type']:
                    curr_obj_dict['geological_type'] = "top"
                else:
                    curr_obj_dict['geological_type'] = "undef"

        elif clean_line[0] == 'GEOLOGICAL_FEATURE':
            curr_obj_dict['geological_feature'] = ("_".join(clean_line[1:]))

        elif clean_line[0] == 'PROPERTIES':
            """Populate the list of property names, the properties number, and initialize the VTK arrays."""
            for prop in clean_line[1:]:
                curr_obj_dict['properties_names'].append(prop)
            properties_number = len(curr_obj_dict['properties_names'])
            for i in range(properties_number):
                new_prop = vtkFloatArray()
                curr_obj_properties_collection.AddItem(new_prop)
                curr_obj_properties_collection.GetItem(i).SetName(curr_obj_dict['properties_names'][i])

        elif clean_line[0] == 'ESIZES':
            ESZ_str = clean_line[1:]
            for i in range(len(ESZ_str)):
                curr_obj_dict['properties_components'].append(int(ESZ_str[i]))
                curr_obj_properties_collection.GetItem(i).SetNumberOfComponents(int(ESZ_str[i]))

        elif clean_line[0] == 'SUBVSET':  # see if and how to start a new SUBVSET part here
            pass

        elif clean_line[0] == 'ILINE':  # see if and how to start a new ILINE part here
            pass

        elif clean_line[0] == 'VRTX':
            curr_obj_points.InsertPoint(int(clean_line[1]) - 1, float(clean_line[2]), float(clean_line[3]), float(clean_line[4]))  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK

        elif clean_line[0] == 'PVRTX':
            curr_obj_points.InsertPoint(int(clean_line[1]) - 1, float(clean_line[2]), float(clean_line[3]), float(clean_line[4]))  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK
            if properties_number > 0:
                """Now we set values in the properties float arrays"""
                """_____________Check if all is OK here with vector properties_________________________________________________"""
                i = 5  # i = 5 since the first five elements have already been read: PVRTX, id, X, Y, Z
                for j in range(properties_number):
                    this_prop = curr_obj_properties_collection.GetItem(j)
                    if curr_obj_dict['properties_components'][j] == 1:
                        this_prop.InsertTuple1(int(clean_line[1]) - 1,
                                               float(clean_line[i]))
                        i = i + 1
                    elif curr_obj_dict['properties_components'][j] == 2:
                        this_prop.InsertTuple2(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]))
                        i = i + 2
                    elif curr_obj_dict['properties_components'][j] == 3:
                        this_prop.InsertTuple3(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]),
                                               float(clean_line[i + 2]))
                        i = i + 3
                    elif curr_obj_dict['properties_components'][j] == 4:
                        this_prop.InsertTuple4(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]),
                                               float(clean_line[i + 2]),
                                               float(clean_line[i + 3]))
                        i = i + 4
                    elif curr_obj_dict['properties_components'][j] == 6:
                        this_prop.InsertTuple4(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]),
                                               float(clean_line[i + 2]),
                                               float(clean_line[i + 3]),
                                               float(clean_line[i + 4]),
                                               float(clean_line[i + 5]))
                        i = i + 6
                    elif curr_obj_dict['properties_components'][j] == 9:
                        this_prop.InsertTuple4(int(clean_line[1]) - 1,
                                               float(clean_line[i]),
                                               float(clean_line[i + 1]),
                                               float(clean_line[i + 2]),
                                               float(clean_line[i + 3]),
                                               float(clean_line[i + 4]),
                                               float(clean_line[i + 5]),
                                               float(clean_line[i + 6]),
                                               float(clean_line[i + 7]),
                                               float(clean_line[i + 8]))
                        i = i + 9
                    else:
                        """Discard property if it is not 1D, 2D, 3D, 4D, 6D or 9D"""
                        i = i + curr_obj_dict['properties_components'][j]
                        curr_obj_dict['properties_names'] = curr_obj_dict['properties_names'].remove(j)
                        properties_number = properties_number - 1
                        curr_obj_dict['properties_components'].remove(j)
                        curr_obj_properties_collection.RemoveItem(j)

        elif clean_line[0] == 'ATOM':
            # atom_id = int(clean_line[1]) - 1
            # vrtx_id = int(clean_line[2]) - 1
            pass

        elif clean_line[0] == 'SEG':
            line = vtkLine()
            line.GetPointIds().SetId(0, int(clean_line[1]) - 1)  # "-1" since first vertex has index 0 in VTK
            line.GetPointIds().SetId(1, int(clean_line[2]) - 1)
            curr_obj_cells.InsertNextCell(line)

        elif clean_line[0] == 'END':
            """When END reached, process the arrays and write the VTK entity with properties to the project geol_coll"""
            entity_counter += 1  # update entity counter

            """Write points and cells TO VTK OBJECT"""
            if curr_obj_dict['topological_type'] == 'XsVertexSet':
                self.TextTerminal.appendPlainText("Importing Gocad VSet (VertexSet) as a PolyData 0D in VTK with name: " + curr_obj_dict['name'])
                curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
                """Vertex cells, one for each point, are added here."""
                for pid in range(curr_obj_dict['vtk_obj'].GetNumberOfPoints()):
                    vertex = vtkVertex()
                    vertex.GetPointIds().SetId(0, pid)
                    curr_obj_cells.InsertNextCell(vertex)
                curr_obj_dict['vtk_obj'].SetVerts(curr_obj_cells)

            elif curr_obj_dict['topological_type'] == 'XsPolyLine':
                self.TextTerminal.appendPlainText("Importing GOCAD PLine (PolyLine) as a PolyData 1D in VTK with name: " + curr_obj_dict['name'])
                curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
                curr_obj_dict['vtk_obj'].SetLines(curr_obj_cells)

            if properties_number > 0:
                for i in range(properties_number):
                    curr_obj_dict['vtk_obj'].GetPointData().AddArray(curr_obj_properties_collection.GetItem(i))

            """Add current_entity to entities collection"""
            self.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
            del curr_obj_points
            del curr_obj_cells
            del curr_obj_properties_collection
            del curr_obj_dict

            """Closing message"""
            self.TextTerminal.appendPlainText("Object n. " + str(entity_counter) + " saved")

    n_entities_after = self.geol_coll.get_number_of_entities()
    self.TextTerminal.appendPlainText("Entities before importing: " + str(n_entities_before))
    self.TextTerminal.appendPlainText("Entities after importing: " + str(n_entities_after))
    self.TextTerminal.appendPlainText("Entities imported: " + str(entity_counter))


def gocad2vtk_boundary(self=None, in_file_name=None, uid_from_name=None):
    """
    Read a GOCAD ASCII file and add, to the boundary_coll BoundaryCollection(), all the
    polyline and triangulated surfaces as VTK polydata entities.
    <self> is the calling ProjectWindow() instance.
    """
    # """Define import options."""
    # scenario_default = input_text_dialog(parent=None, title="Scenario", label="Default scenario", default_text="undef")
    # if not scenario_default:
    #     scenario_default = "undef"
    # geological_type_default = input_combo_dialog(parent=None, title="Geological type", label="Default geological type", choice_list=GeologicalCollection.valid_geological_types)
    # if not geological_type_default:
    #     geological_type_default = "undef"
    # geological_feature_from_name = options_dialog(title="Feature from name", message="Get geological feature from object name if not defined in file", yes_role="Yes", no_role="No", reject_role=None)
    # if geological_feature_from_name == 0:
    #     geological_feature_from_name = True
    # else:
    #     geological_feature_from_name = False
    """Open input file"""
    fin = open(in_file_name, 'rt')
    """Number of entities before importing________________________________"""
    n_entities_before = self.boundary_coll.get_number_of_entities()
    """Initialize entity_counter"""
    entity_counter = 0
    """Parse fin file"""
    for line in fin:
        """Read one line from file."""
        clean_line = line.strip().split()

        """The effect of the following if/elif cascade is to loop for every single object marked by
        the GOCAD keyword, reading the lines that we want to import and skipping the others."""
        if clean_line[0] == 'GOCAD':
            """A new entity starts here in a GOCAD file, so here we create a new empty dictionary,
            then we will fill its components in the next lines. Use deepcopy otherwise the
            original dictionary would be altered."""
            curr_obj_dict = deepcopy(BoundaryCollection.entity_dict)
            # curr_obj_dict['scenario'] = scenario_default

            """Store uid and topological type of new entity."""
            curr_obj_dict['uid'] = str(uuid.uuid4())

            """Create the empty vtk object with class = topological_type."""
            # if clean_line[1] == 'VSet':
            #     curr_obj_dict['topological_type'] = 'VertexSet'
            #     curr_obj_dict['vtk_obj'] = VertexSet()
            #     curr_obj_dict['geological_type'] = geological_type_default
            if clean_line[1] == 'PLine':
                curr_obj_dict['topological_type'] = 'PolyLine'
                curr_obj_dict['vtk_obj'] = PolyLine()
                # curr_obj_dict['geological_type'] = geological_type_default
            elif clean_line[1] == 'TSurf':
                curr_obj_dict['topological_type'] = 'TriSurf'
                curr_obj_dict['vtk_obj'] = TriSurf()
                # curr_obj_dict['geological_type'] = geological_type_default
            else:
                """Here topological types different from the allowed ones are handled.
                At the moment THIS WILL CAUSE ERRORS - KEEP THIS MESSAGE JUST FOR DEBUGGING.
                This must be reimplementende in sucha way that, is non-valid objects are found,
                the file reader jumps to the next line starting with the 'GOCAD' keyword (if any)."""
                self.TextTerminal.appendPlainText("gocad2vtk - entity type not recognized ERROR.")

            """Create empty arrays for coordinates and topology and a counter for properties."""
            curr_obj_points = vtkPoints()
            curr_obj_cells = vtkCellArray()
            # curr_obj_properties_collection = vtkDataArrayCollection()
            # properties_number = 0

        elif 'name:' in clean_line[0]:
            if clean_line[0] == 'name:':
                """standard import"""
                curr_obj_dict['name'] = ("_".join(clean_line[1:]))  # see if a suffix must be added to split multipart
                # if geological_feature_from_name:
                #     curr_obj_dict['geological_feature'] = curr_obj_dict['name']
            else:
                """solves a bug in Move that does not add a space after name: """
                curr_obj_dict['name'] = ("_".join(clean_line[:]))
                curr_obj_dict['name'] = curr_obj_dict['name'][5:]  # this removes 'name:'
                # if geological_feature_from_name:
                #     curr_obj_dict['geological_feature'] = curr_obj_dict['name']
            if uid_from_name:
                curr_obj_dict['uid'] = curr_obj_dict['name']

        # elif clean_line[0] == 'GEOLOGICAL_TYPE':
        #     curr_obj_dict['geological_type'] = ("_".join(clean_line[1:])).lower()
        #     if curr_obj_dict['geological_type'] not in GeologicalCollection.valid_geological_types:
        #         if "Fault" in curr_obj_dict['geological_type']:
        #             curr_obj_dict['geological_type'] = "fault"
        #         elif "fault" in curr_obj_dict['geological_type']:
        #             curr_obj_dict['geological_type'] = "fault"
        #         elif  "Horizon" in curr_obj_dict['geological_type']:
        #             curr_obj_dict['geological_type'] = "top"
        #         else:
        #             curr_obj_dict['geological_type'] = "undef"
        #
        # elif clean_line[0] == 'GEOLOGICAL_FEATURE':
        #     curr_obj_dict['geological_feature'] = ("_".join(clean_line[1:]))
        #
        # elif clean_line[0] == 'PROPERTIES':
        #     """Populate the list of property names, the properties number, and initialize the VTK arrays."""
        #     for prop in clean_line[1:]:
        #         curr_obj_dict['properties_names'].append(prop)
        #     properties_number = len(curr_obj_dict['properties_names'])
        #     for i in range(properties_number):
        #         new_prop = vtkFloatArray()
        #         curr_obj_properties_collection.AddItem(new_prop)
        #         curr_obj_properties_collection.GetItem(i).SetName(curr_obj_dict['properties_names'][i])
        #
        # elif clean_line[0] == 'ESIZES':
        #     ESZ_str = clean_line[1:]
        #     for i in range(len(ESZ_str)):
        #         curr_obj_dict['properties_components'].append(int(ESZ_str[i]))
        #         curr_obj_properties_collection.GetItem(i).SetNumberOfComponents(int(ESZ_str[i]))

        elif clean_line[0] == 'SUBVSET':  # see if and how to start a new SUBVSET part here
            pass

        elif clean_line[0] == 'ILINE':  # see if and how to start a new ILINE part here
            pass

        elif clean_line[0] == 'TFACE':  # see if and how to start a new TFACE part here
            pass

        elif (clean_line[0] == 'VRTX') or (clean_line[0] == 'PVRTX'):
            """VRTX or PVRTX is the same here since properties are not imported."""
            curr_obj_points.InsertPoint(int(clean_line[1]) - 1, float(clean_line[2]), float(clean_line[3]), float(clean_line[4]))  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK

        # elif clean_line[0] == 'PVRTX':
        #     curr_obj_points.InsertPoint(int(clean_line[1]) - 1, float(clean_line[2]), float(clean_line[3]), float(clean_line[4]))  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK
        #     if properties_number > 0:
        #         """Now we set values in the properties float arrays"""
        #         """_____________Check if all is OK here with vector properties_________________________________________________"""
        #         i = 5  # i = 5 since the first five elements have already been read: PVRTX, id, X, Y, Z
        #         for j in range(properties_number):
        #             this_prop = curr_obj_properties_collection.GetItem(j)
        #             if curr_obj_dict['properties_components'][j] == 1:
        #                 this_prop.InsertTuple1(int(clean_line[1]) - 1,
        #                                        float(clean_line[i]))
        #                 i = i + 1
        #             elif curr_obj_dict['properties_components'][j] == 2:
        #                 this_prop.InsertTuple2(int(clean_line[1]) - 1,
        #                                        float(clean_line[i]),
        #                                        float(clean_line[i + 1]))
        #                 i = i + 2
        #             elif curr_obj_dict['properties_components'][j] == 3:
        #                 this_prop.InsertTuple3(int(clean_line[1]) - 1,
        #                                        float(clean_line[i]),
        #                                        float(clean_line[i + 1]),
        #                                        float(clean_line[i + 2]))
        #                 i = i + 3
        #             elif curr_obj_dict['properties_components'][j] == 4:
        #                 this_prop.InsertTuple4(int(clean_line[1]) - 1,
        #                                        float(clean_line[i]),
        #                                        float(clean_line[i + 1]),
        #                                        float(clean_line[i + 2]),
        #                                        float(clean_line[i + 3]))
        #                 i = i + 4
        #             elif curr_obj_dict['properties_components'][j] == 6:
        #                 this_prop.InsertTuple4(int(clean_line[1]) - 1,
        #                                        float(clean_line[i]),
        #                                        float(clean_line[i + 1]),
        #                                        float(clean_line[i + 2]),
        #                                        float(clean_line[i + 3]),
        #                                        float(clean_line[i + 4]),
        #                                        float(clean_line[i + 5]))
        #                 i = i + 6
        #             elif curr_obj_dict['properties_components'][j] == 9:
        #                 this_prop.InsertTuple4(int(clean_line[1]) - 1,
        #                                        float(clean_line[i]),
        #                                        float(clean_line[i + 1]),
        #                                        float(clean_line[i + 2]),
        #                                        float(clean_line[i + 3]),
        #                                        float(clean_line[i + 4]),
        #                                        float(clean_line[i + 5]),
        #                                        float(clean_line[i + 6]),
        #                                        float(clean_line[i + 7]),
        #                                        float(clean_line[i + 8]))
        #                 i = i + 9
        #             else:
        #                 """Discard property if it is not 1D, 2D, 3D, 4D, 6D or 9D"""
        #                 i = i + curr_obj_dict['properties_components'][j]
        #                 curr_obj_dict['properties_names'] = curr_obj_dict['properties_names'].remove(j)
        #                 properties_number = properties_number - 1
        #                 curr_obj_dict['properties_components'].remove(j)
        #                 curr_obj_properties_collection.RemoveItem(j)

        elif clean_line[0] == 'ATOM':
            """NOT YET IMPLEMENTED"""
            # atom_id = int(clean_line[1]) - 1
            # vrtx_id = int(clean_line[2]) - 1
            pass

        elif clean_line[0] == 'SEG':
            line = vtkLine()
            line.GetPointIds().SetId(0, int(clean_line[1]) - 1)  # "-1" since first vertex has index 0 in VTK
            line.GetPointIds().SetId(1, int(clean_line[2]) - 1)
            curr_obj_cells.InsertNextCell(line)

        elif clean_line[0] == 'TRGL':
            triangle = vtkTriangle()
            triangle.GetPointIds().SetId(0, int(clean_line[1]) - 1)  # "-1" since first vertex has index 0 in VTK
            triangle.GetPointIds().SetId(1, int(clean_line[2]) - 1)
            triangle.GetPointIds().SetId(2, int(clean_line[3]) - 1)
            curr_obj_cells.InsertNextCell(triangle)

        elif clean_line[0] == 'END':
            """When END reached, process the arrays and write the VTK entity with properties to the project geol_coll"""
            entity_counter += 1  # update entity counter

            """Write points and cells TO VTK OBJECT"""
            # if curr_obj_dict['topological_type'] == 'VertexSet':
            #     self.TextTerminal.appendPlainText("Importing Gocad VSet (VertexSet) as a PolyData 0D in VTK with name: " + curr_obj_dict['name'])
            #     curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
            #     """Vertex cells, one for each point, are added here."""
            #     for pid in range(curr_obj_dict['vtk_obj'].GetNumberOfPoints()):
            #         vertex = vtkVertex()
            #         vertex.GetPointIds().SetId(0, pid)
            #         curr_obj_cells.InsertNextCell(vertex)
            #     curr_obj_dict['vtk_obj'].SetVerts(curr_obj_cells)
            #
            if curr_obj_dict['topological_type'] == 'PolyLine':
                self.TextTerminal.appendPlainText("Importing GOCAD PLine (PolyLine) as a PolyData 1D in VTK with name: " + curr_obj_dict['name'])
                curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
                curr_obj_dict['vtk_obj'].SetLines(curr_obj_cells)

            elif curr_obj_dict['topological_type'] == 'TriSurf':
                self.TextTerminal.appendPlainText("Importing GOCAD TSurf (TriSurf) as a PolyData 2D in VTK with name: " + curr_obj_dict['name'])
                curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
                curr_obj_dict['vtk_obj'].SetPolys(curr_obj_cells)

            # if properties_number > 0:
            #     for i in range(properties_number):
            #         curr_obj_dict['vtk_obj'].GetPointData().AddArray(curr_obj_properties_collection.GetItem(i))

            """Add current_entity to entities collection"""
            self.boundary_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
            del curr_obj_points
            del curr_obj_cells
            # del curr_obj_properties_collection
            del curr_obj_dict

            """Closing message"""
            self.TextTerminal.appendPlainText("Object n. " + str(entity_counter) + " saved")

    n_entities_after = self.boundary_coll.get_number_of_entities()
    self.TextTerminal.appendPlainText("Entities before importing: " + str(n_entities_before))
    self.TextTerminal.appendPlainText("Entities after importing: " + str(n_entities_after))
    self.TextTerminal.appendPlainText("Entities imported: " + str(entity_counter))


def vtk2gocad(self=None, out_file_name=None):
    """Export a GOCAD ASCII file with all the pointsets, polylines, and triangulated surfaces included, as VTK entities,
    in the self.geol_coll GeologicalCollection(), where <self> is the calling ProjectWindow() instance."""
    """Open file"""
    fout = open(out_file_name, 'w')
    """Write entities"""
    for uid in self.geol_coll.df['uid'].to_list():
        """Loop over uids"""
        topological_type = self.geol_coll.df.loc[self.geol_coll.df['uid'] == uid, 'topological_type'].values[0]
        """Check if this uid is compatible with Gocad Ascii"""
        if topological_type in ['VertexSet', 'PolyLine', 'TriSurf', 'TetraSolid', 'XsVertexSet', 'XsPolyLine']:
            """Get properties and convert to properly formatted strings"""
            color_R = self.geol_coll.get_uid_legend(uid=uid)['color_R'] / 255
            color_G = self.geol_coll.get_uid_legend(uid=uid)['color_G'] / 255
            color_B = self.geol_coll.get_uid_legend(uid=uid)['color_B'] / 255
            geological_feature = self.geol_coll.df.loc[self.geol_coll.df['uid'] == uid, 'geological_feature'].values[0]
            geological_type = self.geol_coll.df.loc[self.geol_coll.df['uid'] == uid, 'geological_type'].values[0]
            geological_age = self.geol_coll.df.loc[self.geol_coll.df['uid'] == uid, 'geological_age'].values[0]
            geological_time = self.a_t_df.loc[self.a_t_df['uid'] == uid, 'geological_time'].values[0]
            properties_names = self.a_t_df.loc[self.a_t_df['uid'] == uid, 'properties_names'].values[0]
            if properties_names != '':
                properties_names = str(properties_names).split(";")
            else:
                properties_names = []
            properties_components = self.a_t_df.loc[self.a_t_df['uid'] == uid, 'properties_components'].values[0]
            if properties_components != '':
                properties_components = str(properties_components).split(";")
            else:
                properties_components = []
            """Write header for each uid"""
            fout.write('GOCAD ' + topological_type + ' 1\n')
            fout.write('HEADER {\n')
            fout.write('*solid*color: ' + (f'{color_R:.3f}' + ' ' + f'{color_G:.3f}' + ' ' + f'{color_B:.3f}') + ' 1\n')
            fout.write('name: ' + uid + '\n')  # IMPORTANT: 'name' is uid, not the 'name' shown as a text label that is not unique
            fout.write('}\n')
            fout.write('GEOLOGICAL_FEATURE ' + geological_feature + '\n')
            fout.write('GEOLOGICAL_TYPE ' + geological_type + '\n')
            fout.write('STRATIGRAPHIC_POSITION ' + geological_age + ' ' + str(geological_time) + '\n')
            """Options for properties"""
            if properties_names:
                fout.write('PROPERTIES ' + (' '.join(map(str, properties_names))) + '\n')
                fout.write('ESIZES ' + (' '.join(map(str, properties_components))) + '\n')
                """Build PVRTX matrix here"""
                """_____________Check if there is an error here with vector properties_________________________________________________"""
                pvrtx_mtx = self.geol_coll.get_uid_vtk_obj(uid).points
                for property_name in properties_names:
                    pvrtx_mtx = np_column_stack([pvrtx_mtx, self.geol_coll.get_uid_vtk_obj(uid).get_point_data(property_name)])
            else:
                """Build VRTX matrix here"""
                vrtx_mtx = self.geol_coll.get_uid_vtk_obj(uid).points
            """Options for different topological types"""
            if topological_type in ['VertexSet', 'XsVertexSet']:
                fout.write('SUBVSET\n')
                """No connectivity matrix in this case."""
            elif topological_type in ['PolyLine', 'XsPolyLine']:
                fout.write('ILINE\n')
                """Build connectivity matrix here."""
                connectivity = self.geol_coll.get_uid_vtk_obj(uid).cells
            elif topological_type in ['TriSurf']:
                fout.write('TFACE\n')
                """Build connectivity matrix here."""
                connectivity = self.geol_coll.get_uid_vtk_obj(uid).cells
            elif topological_type in ['TetraSolid']:
                fout.write('TVOLUME\n')
                """Build connectivity matrix here."""
                connectivity = self.geol_coll.get_uid_vtk_obj(uid).cells
            """Write VRTX or PVRTX"""
            if properties_names:
                for row in range(np_shape(pvrtx_mtx)[0]):
                    data_row = ' '.join(['{}'.format(cell) for cell in pvrtx_mtx[row, :]])
                    fout.write('PVRTX ' + str(
                        row + 1) + ' ' + data_row + '\n')  # row+1 since indexes in Gocad Ascii start from 1
                del pvrtx_mtx
            else:
                for row in range(np_shape(vrtx_mtx)[0]):
                    data_row = ' '.join(['{}'.format(cell) for cell in vrtx_mtx[row, :]])
                    fout.write('VRTX ' + str(
                        row + 1) + ' ' + data_row + '\n')  # row+1 since indexes in Gocad Ascii start from 1
                del vrtx_mtx
            """Write connectivity"""
            if topological_type in ['VertexSet', 'XsVertexSet']:
                pass
            elif topological_type in ['PolyLine', 'XsPolyLine']:
                for row in range(np_shape(connectivity)[0]):
                    data_row = ' '.join(['{}'.format(cell + 1) for cell in connectivity[row,:]])  # cell+1 since indexes in Gocad Ascii start from 1 - do not alter connectivity that is a shallow copy
                    fout.write("SEG " + data_row + "\n")
                del connectivity
            elif topological_type in ['TriSurf']:
                for row in range(np_shape(connectivity)[0]):
                    data_row = ' '.join(['{}'.format(cell + 1) for cell in connectivity[row,:]])  # cell+1 since indexes in Gocad Ascii start from 1 - do not alter connectivity that is a shallow copy
                    fout.write("TRGL " + data_row + "\n")
                del connectivity
            elif topological_type in ['TetraSolid']:
                for row in range(np_shape(connectivity)[0]):
                    data_row = ' '.join(['{}'.format(cell + 1) for cell in connectivity[row,:]])  # cell+1 since indexes in Gocad Ascii start from 1 - do not alter connectivity that is a shallow copy
                    fout.write("TETRA " + data_row + "\n")
                del connectivity
            fout.write('END\n')
        else:
            print("Entity ", uid, "not supported in Gocad Ascii")
    fout.close()
