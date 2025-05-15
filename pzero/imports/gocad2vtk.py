"""gocad2vtk.py
PZero© Andrea Bistacchi"""

from uuid import uuid4
from copy import deepcopy

from numpy import column_stack as np_column_stack
from numpy import shape as np_shape
from numpy import rad2deg as np_rad2deg
from numpy import arctan2 as np_arctan2
from numpy import sqrt as np_sqrt

from vtk import (
    vtkPoints,
    vtkCellArray,
    vtkDataArrayCollection,
    vtkFloatArray,
    vtkLine,
    vtkTriangle,
    vtkVertex,
    vtkAppendPolyData,
)
from vtkmodules.numpy_interface.dataset_adapter import WrapDataObject

from pzero.collections.boundary_collection import BoundaryCollection
from pzero.collections.geological_collection import GeologicalCollection
from pzero.entities_factory import (
    VertexSet,
    PolyLine,
    TriSurf,
    XsVertexSet,
    XsPolyLine,
    Plane,
)
from pzero.helpers.helper_dialogs import (
    input_text_dialog,
    input_combo_dialog,
    options_dialog,
)
from pzero.helpers.helper_functions import best_fitting_plane
from pzero.collections.xsection_collection import XSectionCollection

# """We import only come Gocad object attributes.
# Other Gocad ASCII properties/fields/keys not implemented in PZero are:
#    CRS-related -> we use a single homogeneous CRS in every
#    project and conversions must be performed before importing data.
#    'CRS_name'
#    'CRS_projection'
#    'CRS_datum'
#    'CRS_axis_name'
#    'CRS_axis_unit'
#    'CRS_z_positive'
#    STRATIGRAPHIC_POSITION -> this in Gocad includes geological age (string) and time
#    (number), but in PZero these are defined in the legend for each geological feature.
#    Properties -> some of these can be retrieved from properties stored in VTK
#    arrays, and for units the same as for CRS applies (generally we use SI units).
#    'properties_no_data_values'
#    'properties_components_sum': int(0),
#    'properties_units': []
#    Properties-related keywords, probably redundant.
#     'PROP_LEGAL_RANGES'
#     'PROPERTY_CLASSES'
#     'PROPERTY_KINDS'
#     'PROPERTY_SUBCLASSES'
#     'INTERPOLATION_METHODS'
#     'PROPERTY_CLASS_HEADER'
#     'kind:'
#     'unit:'
#     'is_z:'
#    Cosmetic rendering- or legend-related properties/keywords.
#    '*atoms*size:'
#    '*atoms*color:'
#    'use_feature_color:'
#    'atoms:'
#    '*painted*variable:'
#    '*painted:'
#    '*atoms*symbol:'
#    'last_selected_folder:'
#    '*vectors3d*variable:'
#    '*tensors3d*variable:'
#    'vectors3d:'
#    '*vectors3d*color:'
#    '*vectors3d*arrow_size:'
#    '*vectors3d*rescale:'
#   '*vectors3d*mode:'
#    '*vectors3d*arrow:'
#     '*solid*color:'
#     'mesh:'
#     'parts:'
#     'pclip:'
#     'low_clip:'
#     'high_clip:'
#     'colormap:'
#     When importing we do not consider the following
#     keywords that could be important.
#     'BSTONE'
#     'BORDER'


def gocad2vtk(self=None, in_file_name=None, uid_from_name=None):
    """
    Read a GOCAD ASCII file and add, to the geol_coll GeologicalCollection(), all the
    pointset, polyline, triangulated surfaces as VTK polydata entities.
    <self> is the calling ProjectWindow() instance.
    """
    # Define import options.
    scenario_default = input_text_dialog(
        parent=None, title="Scenario", label="Default scenario", default_text="undef"
    )
    if not scenario_default:
        scenario_default = "undef"
    role_default = input_combo_dialog(
        parent=None,
        title="Role",
        label="Default role",
        choice_list=self.geol_coll.valid_roles,
    )
    if not role_default:
        role_default = "undef"
    feature_from_name = options_dialog(
        title="Feature from name",
        message="Get geological feature from object name if not defined in file",
        yes_role="Yes",
        no_role="No",
        reject_role=None,
    )
    if feature_from_name == 0:
        feature_from_name = True
    else:
        feature_from_name = False
    reset_legend = options_dialog(
        title="Legend reset",
        message="Reset color in legend from object properties defined in file",
        yes_role="Yes",
        no_role="No",
        reject_role=None,
    )
    if reset_legend == 0:
        reset_legend = True
    else:
        reset_legend = False
    # Open input file as fin.
    fin = open(in_file_name, "rt")
    # Record number of entities before importing and initialize entity_counter
    n_entities_before = self.geol_coll.get_number_of_entities
    entity_counter = 0
    # Parse fin file.
    for line in fin:
        # Read one line from file ad decide what to do with it.
        # The effect of the following if/elif cascade is to loop for every single object marked by
        # GOCAD keywords (see above), reading the lines that we want to import and skipping the others.
        clean_line = line.strip().split()
        if clean_line[0] == "GOCAD":
            # A new entity starts here in a GOCAD file, so here we create a new empty dictionary,
            # then we will fill its components in the next lines. Use deepcopy otherwise the
            # original dictionary would be altered.
            curr_obj_dict = deepcopy(self.geol_coll.entity_dict)
            curr_obj_dict["name"] = "undef"
            curr_obj_dict["scenario"] = scenario_default
            curr_obj_dict["role"] = role_default

            # Store uid of new entity.
            curr_obj_dict["uid"] = str(uuid4())

            # Create the empty vtk object with class = topology.
            if clean_line[1] == "VSet":
                curr_obj_dict["topology"] = "VertexSet"
                curr_obj_dict["vtk_obj"] = VertexSet()
            elif clean_line[1] == "PLine":
                curr_obj_dict["topology"] = "PolyLine"
                curr_obj_dict["vtk_obj"] = PolyLine()
            elif clean_line[1] == "TSurf":
                curr_obj_dict["topology"] = "TriSurf"
                curr_obj_dict["vtk_obj"] = TriSurf()
            else:
                # Here topology different from the allowed ones are handled.
                # At the moment THIS WILL CAUSE ERRORS - KEEP THIS MESSAGE JUST FOR DEBUGGING.
                # This must be reimplemented in such a way that, if non-valid objects are found,
                # the file reader jumps to the next line starting with the 'GOCAD' keyword (if any).
                self.print_terminal("gocad2vtk - entity type not recognized ERROR.")

            # Create empty arrays for coordinates and topology and a counter for properties.
            curr_obj_points = vtkPoints()
            curr_obj_cells = vtkCellArray()
            curr_obj_properties_collection = vtkDataArrayCollection()
            properties_number = 0

            # Initialize color
            curr_obj_color_r = None
            curr_obj_color_g = None
            curr_obj_color_b = None

        elif "*solid*color:" in clean_line[0]:
            try:
                curr_obj_color_r = float(round(float(clean_line[1]) * 255))
                curr_obj_color_g = float(round(float(clean_line[2]) * 255))
                curr_obj_color_b = float(round(float(clean_line[3]) * 255))
            except:
                pass

        elif "name:" in clean_line[0]:
            # "name:" has the same meaning as "name" in PZero
            if line[:5] == "name:":
                # this check solves a problem with a property sometimes called "gname"
                if clean_line[0] == "name:":
                    # standard import
                    curr_obj_dict["name"] = "_".join(
                        clean_line[1:]
                    )  # see if a suffix must be added to split multipart
                    if feature_from_name:
                        curr_obj_dict["feature"] = curr_obj_dict["name"]
                else:
                    # solves a bug in some other software that does not add a space after name:
                    curr_obj_dict["name"] = "_".join(clean_line[:])
                    curr_obj_dict["name"] = curr_obj_dict["name"][
                        5:
                    ]  # this removes 'name:'
                    if feature_from_name:
                        curr_obj_dict["feature"] = curr_obj_dict["name"]
                if uid_from_name:
                    curr_obj_dict["uid"] = curr_obj_dict["name"]

        elif clean_line[0] == "GEOLOGICAL_TYPE":
            # "GEOLOGICAL_TYPE" has the same meaning as "role" in PZero
            curr_obj_dict["role"] = ("_".join(clean_line[1:])).lower()
            if curr_obj_dict["role"] not in self.geol_coll.valid_roles:
                if "Fault" in curr_obj_dict["role"]:
                    curr_obj_dict["role"] = "fault"
                elif "Horizon" in curr_obj_dict["role"]:
                    curr_obj_dict["role"] = "top"
                else:
                    curr_obj_dict["role"] = "undef"

        elif clean_line[0] == "GEOLOGICAL_FEATURE":
            # "GEOLOGICAL_FEATURE" has the same meaning as "feature" in PZero
            curr_obj_dict["feature"] = "_".join(clean_line[1:])

        elif clean_line[0] == "PROPERTIES":
            # Populate the list of property names, the properties number, and initialize the VTK arrays.
            for prop in clean_line[1:]:
                curr_obj_dict["properties_names"].append(prop)
            properties_number = len(curr_obj_dict["properties_names"])
            for i in range(properties_number):
                new_prop = vtkFloatArray()
                curr_obj_properties_collection.AddItem(new_prop)
                curr_obj_properties_collection.GetItem(i).SetName(
                    curr_obj_dict["properties_names"][i]
                )

        elif clean_line[0] == "ESIZES":
            # Populate the list of property components.
            ESZ_str = clean_line[1:]
            for i in range(len(ESZ_str)):
                curr_obj_dict["properties_components"].append(int(ESZ_str[i]))
                curr_obj_properties_collection.GetItem(i).SetNumberOfComponents(
                    int(ESZ_str[i])
                )

        elif clean_line[0] == "SUBVSET":
            # see in the future if and how to start a new SUBVSET part here
            pass

        elif clean_line[0] == "ILINE":
            # see in the future if and how to start a new ILINE part here
            pass

        elif clean_line[0] == "TFACE":
            # see in the future if and how to start a new TFACE part here
            pass

        elif clean_line[0] in ["VRTX", "PVRTX", "SEG", "TRGL", "ATOM"]:
            # This inner condition is required to handle multipart entities.
            if clean_line[0] == "VRTX":
                # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK
                curr_obj_points.InsertPoint(
                    int(clean_line[1]) - 1,
                    float(clean_line[2]),
                    float(clean_line[3]),
                    float(clean_line[4]),
                )

            elif clean_line[0] == "PVRTX":
                # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK
                curr_obj_points.InsertPoint(
                    int(clean_line[1]) - 1,
                    float(clean_line[2]),
                    float(clean_line[3]),
                    float(clean_line[4]),
                )
                if properties_number > 0:
                    # Now we set values in the properties float arrays
                    # _____________Check if all is OK here with vector properties_______________________________________
                    i = 5  # i = 5 since the first five elements have already been read: PVRTX, id, X, Y, Z
                    for j in range(properties_number):
                        this_prop = curr_obj_properties_collection.GetItem(j)
                        if curr_obj_dict["properties_components"][j] == 1:
                            this_prop.InsertTuple1(
                                int(clean_line[1]) - 1, float(clean_line[i])
                            )
                            i = i + 1
                        elif curr_obj_dict["properties_components"][j] == 2:
                            this_prop.InsertTuple2(
                                int(clean_line[1]) - 1,
                                float(clean_line[i]),
                                float(clean_line[i + 1]),
                            )
                            i = i + 2
                        elif curr_obj_dict["properties_components"][j] == 3:
                            this_prop.InsertTuple3(
                                int(clean_line[1]) - 1,
                                float(clean_line[i]),
                                float(clean_line[i + 1]),
                                float(clean_line[i + 2]),
                            )
                            i = i + 3
                        elif curr_obj_dict["properties_components"][j] == 4:
                            this_prop.InsertTuple4(
                                int(clean_line[1]) - 1,
                                float(clean_line[i]),
                                float(clean_line[i + 1]),
                                float(clean_line[i + 2]),
                                float(clean_line[i + 3]),
                            )
                            i = i + 4
                        elif curr_obj_dict["properties_components"][j] == 6:
                            this_prop.InsertTuple4(
                                int(clean_line[1]) - 1,
                                float(clean_line[i]),
                                float(clean_line[i + 1]),
                                float(clean_line[i + 2]),
                                float(clean_line[i + 3]),
                                float(clean_line[i + 4]),
                                float(clean_line[i + 5]),
                            )
                            i = i + 6
                        elif curr_obj_dict["properties_components"][j] == 9:
                            this_prop.InsertTuple4(
                                int(clean_line[1]) - 1,
                                float(clean_line[i]),
                                float(clean_line[i + 1]),
                                float(clean_line[i + 2]),
                                float(clean_line[i + 3]),
                                float(clean_line[i + 4]),
                                float(clean_line[i + 5]),
                                float(clean_line[i + 6]),
                                float(clean_line[i + 7]),
                                float(clean_line[i + 8]),
                            )
                            i = i + 9
                        else:
                            # Discard property if it is not 1D, 2D, 3D, 4D, 6D or 9D.
                            i = i + curr_obj_dict["properties_components"][j]
                            curr_obj_dict["properties_names"] = curr_obj_dict[
                                "properties_names"
                            ].remove(j)
                            properties_number = properties_number - 1
                            curr_obj_dict["properties_components"].remove(j)
                            curr_obj_properties_collection.RemoveItem(j)

            elif clean_line[0] == "ATOM":
                # ATOM id1 id2 (where id1 > id2) indicates a vertex with index id1 that shares the same XYZ position
                # as a previous vertex with id2. This is used in Gocad to create co-located vertexes that are
                # disconnected in topological sense. In PZero we create two independent vertexes with the same
                # coordinates.
                this_atom_id = int(clean_line[1]) - 1
                from_vrtx_id = int(clean_line[2]) - 1
                curr_obj_points.InsertPoint(
                    this_atom_id, curr_obj_points.GetPoint(from_vrtx_id)
                )

            elif clean_line[0] == "SEG":
                line = vtkLine()
                line.GetPointIds().SetId(
                    0, int(clean_line[1]) - 1
                )  # "-1" since first vertex has index 0 in VTK
                line.GetPointIds().SetId(1, int(clean_line[2]) - 1)
                curr_obj_cells.InsertNextCell(line)

            elif clean_line[0] == "TRGL":
                triangle = vtkTriangle()
                triangle.GetPointIds().SetId(
                    0, int(clean_line[1]) - 1
                )  # "-1" since first vertex has index 0 in VTK
                triangle.GetPointIds().SetId(1, int(clean_line[2]) - 1)
                triangle.GetPointIds().SetId(2, int(clean_line[3]) - 1)
                curr_obj_cells.InsertNextCell(triangle)

        elif clean_line[0] == "BSTONE":
            # NOT YET IMPLEMENTED
            pass

        elif clean_line[0] == "BORDER":
            # NOT YET IMPLEMENTED
            pass

        elif clean_line[0] == "END":
            # When END reached, process the arrays and write the VTK entity with
            # properties to the project geol_coll
            # update entity counter
            entity_counter += 1

            # Write points and cells TO VTK OBJECT
            if curr_obj_dict["topology"] == "VertexSet":
                self.print_terminal(
                    f"Importing Gocad VSet (VertexSet) as a PolyData 0D in VTK with name: {curr_obj_dict['name']}"
                )
                curr_obj_dict["vtk_obj"].SetPoints(curr_obj_points)

                # Vertex cells, one for each point, are added here.
                for pid in range(curr_obj_dict["vtk_obj"].GetNumberOfPoints()):
                    vertex = vtkVertex()
                    vertex.GetPointIds().SetId(0, pid)
                    curr_obj_cells.InsertNextCell(vertex)
                curr_obj_dict["vtk_obj"].SetVerts(curr_obj_cells)

            elif curr_obj_dict["topology"] == "PolyLine":
                self.print_terminal(
                    f"Importing GOCAD PLine (PolyLine) as a PolyData 1D in VTK with name: {curr_obj_dict['name']}"
                )
                curr_obj_dict["vtk_obj"].SetPoints(curr_obj_points)
                curr_obj_dict["vtk_obj"].SetLines(curr_obj_cells)

            elif curr_obj_dict["topology"] == "TriSurf":
                self.print_terminal(
                    f"Importing GOCAD TSurf (TriSurf) as a PolyData 2D in VTK with name: {curr_obj_dict['name']}"
                )
                curr_obj_dict["vtk_obj"].SetPoints(curr_obj_points)
                curr_obj_dict["vtk_obj"].SetPolys(curr_obj_cells)

            if properties_number > 0:
                for i in range(properties_number):
                    curr_obj_dict["vtk_obj"].GetPointData().AddArray(
                        curr_obj_properties_collection.GetItem(i)
                    )

            # print(curr_obj_dict["vtk_obj"])

            # Add current_entity to entities collection, after checking if the entity is valid.
            if curr_obj_dict["vtk_obj"].points_number > 0:
                if curr_obj_dict["topology"] == "VertexSet":
                    self.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
                else:
                    if curr_obj_dict["vtk_obj"].cells_number > 0:
                        self.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
                if reset_legend and curr_obj_color_r:
                    self.geol_coll.set_uid_legend(
                        uid=curr_obj_dict["uid"],
                        color_R=curr_obj_color_r,
                        color_G=curr_obj_color_g,
                        color_B=curr_obj_color_b,
                    )
            del curr_obj_points
            del curr_obj_cells
            del curr_obj_properties_collection
            del curr_obj_dict

            # Closing message
            self.print_terminal(f"Object n. {str(entity_counter)} saved")

    n_entities_after = self.geol_coll.get_number_of_entities
    self.print_terminal(f"Entities before importing: {str(n_entities_before)}")
    self.print_terminal(f"Entities after importing: {str(n_entities_after)}")
    self.print_terminal(f"Entities imported: {str(entity_counter)}")


def gocad2vtk_section(
    self=None,
    in_file_name=None,
    uid_from_name=None,
    x_section_uid=None,
    scenario_default=None,
    role_default=None,
    feature_from_name=None,
    append_opt=None,
):
    """
    Read a GOCAD ASCII file with entities belonging to a single cross-section, and add,
    to the geol_coll GeologicalCollection(), all the
    pointset and polyline VTK polydata entities.
    This is the specific implementation for objects belonging to a cross-section.
    <self> is the calling ProjectWindow() instance.
    """
    # Open input file.
    fin = open(in_file_name, "rt")
    # Number of entities before importing.
    n_entities_before = self.geol_coll.get_number_of_entities
    # Initialize entity_counter and input uids.
    entity_counter = 0
    input_uids = []
    # Parse fin file.
    for line in fin:
        # Read one line from file.
        clean_line = line.strip().split()

        # The effect of the following if/elif cascade is to loop for every single object marked by
        # the GOCAD keyword, reading the lines that we want to import and skipping the others.
        if clean_line[0] == "GOCAD":
            # A new entity starts here in a GOCAD file, so here we create a new empty dictionary,
            # then we will fill its components in the next lines. Use deepcopy otherwise the
            # original dictionary would be altered.
            curr_obj_dict = deepcopy(self.geol_coll.entity_dict)
            curr_obj_dict["x_section"] = x_section_uid
            curr_obj_dict["scenario"] = scenario_default
            # Store uid and topological type of new entity.
            curr_obj_dict["uid"] = str(uuid4())
            input_uids.append(curr_obj_dict["uid"])
            # Create the empty vtk object with class = topological_type.
            if clean_line[1] == "VSet":
                curr_obj_dict["vtk_obj"] = XsVertexSet(
                    x_section_uid=x_section_uid, parent=self
                )
                curr_obj_dict["topology"] = "XsVertexSet"
                curr_obj_dict["role"] = role_default
            elif clean_line[1] == "PLine":
                curr_obj_dict["vtk_obj"] = XsPolyLine(
                    x_section_uid=x_section_uid, parent=self
                )
                curr_obj_dict["topology"] = "XsPolyLine"
                curr_obj_dict["role"] = role_default
            else:
                # Here topological types different from the allowed ones are handled.
                # At the moment THIS WILL CAUSE ERRORS - KEEP THIS MESSAGE JUST FOR DEBUGGING.
                # This must be reimplementende in sucha way that, is non-valid objects are found,
                # the file reader jumps to the next line starting with the 'GOCAD' keyword (if any).
                self.print_terminal("gocad2vtk - entity type not recognized ERROR.")
            # Create empty arrays for coordinates and topology and a counter for properties.
            curr_obj_points = vtkPoints()
            curr_obj_cells = vtkCellArray()
            curr_obj_properties_collection = vtkDataArrayCollection()
            properties_number = 0

        elif "name:" in clean_line[0]:
            if clean_line[0] == "name:":
                # standard import
                curr_obj_dict["name"] = "_".join(
                    clean_line[1:]
                )  # see if a suffix must be added to split multipart
                if feature_from_name:
                    curr_obj_dict["feature"] = curr_obj_dict["name"]
            else:
                # solves a bug in some other software that does not add a space after name:
                curr_obj_dict["name"] = "_".join(clean_line[:])
                curr_obj_dict["name"] = curr_obj_dict["name"][
                    5:
                ]  # this removes 'name:'
                if feature_from_name:
                    curr_obj_dict["feature"] = curr_obj_dict["name"]
            if uid_from_name:
                curr_obj_dict["uid"] = curr_obj_dict["name"]

        elif clean_line[0] == "GEOLOGICAL_TYPE":
            curr_obj_dict["role"] = ("_".join(clean_line[1:])).lower()
            if curr_obj_dict["role"] not in self.geol_coll.valid_roles:
                if "Fault" in curr_obj_dict["role"]:
                    curr_obj_dict["role"] = "fault"
                elif "fault" in curr_obj_dict["role"]:
                    curr_obj_dict["role"] = "fault"
                elif "Horizon" in curr_obj_dict["role"]:
                    curr_obj_dict["role"] = "top"
                else:
                    curr_obj_dict["role"] = "undef"

        elif clean_line[0] == "GEOLOGICAL_FEATURE":
            curr_obj_dict["feature"] = "_".join(clean_line[1:])

        elif clean_line[0] == "PROPERTIES":
            # Populate the list of property names, the properties number, and initialize the VTK arrays.
            for prop in clean_line[1:]:
                curr_obj_dict["properties_names"].append(prop)
            properties_number = len(curr_obj_dict["properties_names"])
            for i in range(properties_number):
                new_prop = vtkFloatArray()
                curr_obj_properties_collection.AddItem(new_prop)
                curr_obj_properties_collection.GetItem(i).SetName(
                    curr_obj_dict["properties_names"][i]
                )

        elif clean_line[0] == "ESIZES":
            ESZ_str = clean_line[1:]
            for i in range(len(ESZ_str)):
                curr_obj_dict["properties_components"].append(int(ESZ_str[i]))
                curr_obj_properties_collection.GetItem(i).SetNumberOfComponents(
                    int(ESZ_str[i])
                )

        elif (
            clean_line[0] == "SUBVSET"
        ):  # see if and how to start a new SUBVSET part here
            pass

        elif clean_line[0] == "ILINE":  # see if and how to start a new ILINE part here
            pass

        elif clean_line[0] == "VRTX":
            curr_obj_points.InsertPoint(
                int(clean_line[1]) - 1,
                float(clean_line[2]),
                float(clean_line[3]),
                float(clean_line[4]),
            )  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK

        elif clean_line[0] == "PVRTX":
            curr_obj_points.InsertPoint(
                int(clean_line[1]) - 1,
                float(clean_line[2]),
                float(clean_line[3]),
                float(clean_line[4]),
            )  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK
            if properties_number > 0:
                # Now we set values in the properties float arrays
                # _____________Check if all is OK here with vector properties_________________________________________________
                i = 5  # i = 5 since the first five elements have already been read: PVRTX, id, X, Y, Z
                for j in range(properties_number):
                    this_prop = curr_obj_properties_collection.GetItem(j)
                    if curr_obj_dict["properties_components"][j] == 1:
                        this_prop.InsertTuple1(
                            int(clean_line[1]) - 1, float(clean_line[i])
                        )
                        i = i + 1
                    elif curr_obj_dict["properties_components"][j] == 2:
                        this_prop.InsertTuple2(
                            int(clean_line[1]) - 1,
                            float(clean_line[i]),
                            float(clean_line[i + 1]),
                        )
                        i = i + 2
                    elif curr_obj_dict["properties_components"][j] == 3:
                        this_prop.InsertTuple3(
                            int(clean_line[1]) - 1,
                            float(clean_line[i]),
                            float(clean_line[i + 1]),
                            float(clean_line[i + 2]),
                        )
                        i = i + 3
                    elif curr_obj_dict["properties_components"][j] == 4:
                        this_prop.InsertTuple4(
                            int(clean_line[1]) - 1,
                            float(clean_line[i]),
                            float(clean_line[i + 1]),
                            float(clean_line[i + 2]),
                            float(clean_line[i + 3]),
                        )
                        i = i + 4
                    elif curr_obj_dict["properties_components"][j] == 6:
                        this_prop.InsertTuple4(
                            int(clean_line[1]) - 1,
                            float(clean_line[i]),
                            float(clean_line[i + 1]),
                            float(clean_line[i + 2]),
                            float(clean_line[i + 3]),
                            float(clean_line[i + 4]),
                            float(clean_line[i + 5]),
                        )
                        i = i + 6
                    elif curr_obj_dict["properties_components"][j] == 9:
                        this_prop.InsertTuple4(
                            int(clean_line[1]) - 1,
                            float(clean_line[i]),
                            float(clean_line[i + 1]),
                            float(clean_line[i + 2]),
                            float(clean_line[i + 3]),
                            float(clean_line[i + 4]),
                            float(clean_line[i + 5]),
                            float(clean_line[i + 6]),
                            float(clean_line[i + 7]),
                            float(clean_line[i + 8]),
                        )
                        i = i + 9
                    else:
                        # Discard property if it is not 1D, 2D, 3D, 4D, 6D or 9D
                        i = i + curr_obj_dict["properties_components"][j]
                        curr_obj_dict["properties_names"] = curr_obj_dict[
                            "properties_names"
                        ].remove(j)
                        properties_number = properties_number - 1
                        curr_obj_dict["properties_components"].remove(j)
                        curr_obj_properties_collection.RemoveItem(j)

        elif clean_line[0] == "ATOM":
            # atom_id = int(clean_line[1]) - 1
            # vrtx_id = int(clean_line[2]) - 1
            pass

        elif clean_line[0] == "SEG":
            line = vtkLine()
            line.GetPointIds().SetId(
                0, int(clean_line[1]) - 1
            )  # "-1" since first vertex has index 0 in VTK
            line.GetPointIds().SetId(1, int(clean_line[2]) - 1)
            curr_obj_cells.InsertNextCell(line)

        elif clean_line[0] == "END":
            # When END reached, process the arrays and write the VTK entity with properties to the project geol_coll
            entity_counter += 1  # update entity counter

            # Write points and cells TO VTK OBJECT
            if curr_obj_dict["topology"] == "XsVertexSet":
                self.print_terminal(
                    f"Importing Gocad VSet (VertexSet) as a PolyData 0D in VTK with name:\n{curr_obj_dict['name']}"
                )
                curr_obj_dict["vtk_obj"].SetPoints(curr_obj_points)
                # Vertex cells, one for each point, are added here.
                for pid in range(curr_obj_dict["vtk_obj"].GetNumberOfPoints()):
                    vertex = vtkVertex()
                    vertex.GetPointIds().SetId(0, pid)
                    curr_obj_cells.InsertNextCell(vertex)
                curr_obj_dict["vtk_obj"].SetVerts(curr_obj_cells)

            elif curr_obj_dict["topology"] == "XsPolyLine":
                self.print_terminal(
                    f"Importing GOCAD PLine (PolyLine) as a PolyData 1D in VTK with name: {curr_obj_dict['name']}"
                )
                curr_obj_dict["vtk_obj"].SetPoints(curr_obj_points)
                curr_obj_dict["vtk_obj"].SetLines(curr_obj_cells)

            if properties_number > 0:
                for i in range(properties_number):
                    curr_obj_dict["vtk_obj"].GetPointData().AddArray(
                        curr_obj_properties_collection.GetItem(i)
                    )

            # Add current_entity to entities collection
            self.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
            del curr_obj_points
            del curr_obj_cells
            del curr_obj_properties_collection
            del curr_obj_dict

            # Closing message
            self.print_terminal(f"Object n. {str(entity_counter)} saved")

    n_entities_after = self.geol_coll.get_number_of_entities
    self.print_terminal(f"Entities before importing: {str(n_entities_before)}")
    self.print_terminal(f"Entities after importing: {str(n_entities_after)}")
    self.print_terminal(f"Entities imported: {str(entity_counter)}")

    if not append_opt:
        # Re-orient XSection only if it is a new one.
        # Create a vtkAppendPolyData filter to merge all input vtk objects.
        vtkappend = vtkAppendPolyData()
        for uid in input_uids:
            vtkappend.AddInputData(self.geol_coll.get_uid_vtk_obj(uid))
        vtkappend.Update()
        append_points = WrapDataObject(vtkappend.GetOutput()).Points

        # Fit new XSection plane.
        # new_xs_plane = Plane()
        # new_xs_plane_origin = reference((0., 0., 0.))
        # new_test = new_xs_plane.ComputeBestFittingPlane(append_points, new_xs_plane_origin, new_xs_plane_normal)
        origin, normal = best_fitting_plane(append_points)
        del vtkappend
        del append_points
        if normal[1] > 0:
            # force NW-SE and SW-NE XSections -> azimuth in 2nd and 1st quadrant
            normal = -normal
        # force normal to be horizontal -> dip = 90 deg
        normal[2] = 0
        normal[0] /= np_sqrt(normal[0] ** 2 + normal[1] ** 2)
        normal[1] /= np_sqrt(normal[0] ** 2 + normal[1] ** 2)
        azimuth = np_rad2deg(np_arctan2(normal[0], normal[1])) - 90
        if azimuth < 0:
            azimuth += 360
        # set normal, azimuth and dip in XSection
        self.xsect_coll.set_uid_normal_x(x_section_uid, normal[0])
        self.xsect_coll.set_uid_normal_y(x_section_uid, normal[1])
        self.xsect_coll.set_uid_normal_z(x_section_uid, 0.0)
        self.xsect_coll.set_uid_azimuth(x_section_uid, azimuth)
    else:
        # Get normal and origin from XSection if it is an old one.
        normal = (
            self.xsect_coll.get_uid_normal_x(x_section_uid),
            self.xsect_coll.get_uid_normal_y(x_section_uid),
            self.xsect_coll.get_uid_normal_z(x_section_uid),
        )
        origin = (
            (
                self.xsect_coll.get_uid_base_x(x_section_uid)
                + self.xsect_coll.get_uid_end_x(x_section_uid)
            )
            / 2,
            (
                self.xsect_coll.get_uid_base_y(x_section_uid)
                + self.xsect_coll.get_uid_end_y(x_section_uid)
            )
            / 2,
            (
                self.xsect_coll.get_uid_top(x_section_uid)
                + self.xsect_coll.get_uid_bottom(x_section_uid)
            )
            / 2,
        )
        azimuth = self.xsect_coll.get_uid_azimuth(x_section_uid)

    # # In any case, project (force) new entities to section plane
    # for uid in input_uids:
    #     project2plane = vtkProjectPointsToPlane()
    #     project2plane.SetProjectionTypeToSpecifiedPlane()
    #     project2plane.SetNormal(normal)
    #     project2plane.SetOrigin(origin)
    #     project2plane.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
    #     # ShallowCopy is the way to copy the new entity into the instance created at the beginning
    #     self.geol_coll.df.loc[self.geol_coll.df["uid"] == uid, "vtk_obj"].tolist()[0].ShallowCopy(project2plane.GetOutput())

    # Create a vtkAppendPolyData filter to merge all vtk objects belonging to this XSection,
    # including new and old entities for in case entities are appended to an old XSection.
    vtkappend_all = vtkAppendPolyData()
    for uid in self.geol_coll.df.loc[
        self.geol_coll.df["x_section"] == x_section_uid, "uid"
    ].tolist():
        vtkappend_all.AddInputData(self.geol_coll.get_uid_vtk_obj(uid))
    vtkappend_all.Update()
    append_points_all = WrapDataObject(vtkappend_all.GetOutput()).Points
    self.xsect_coll.set_uid_base_x(x_section_uid, min(append_points_all[:, 0]))
    self.xsect_coll.set_uid_end_x(x_section_uid, max(append_points_all[:, 0]))
    if azimuth <= 90:
        # case for 1st quadrant
        self.xsect_coll.set_uid_base_y(x_section_uid, min(append_points_all[:, 1]))
        self.xsect_coll.set_uid_end_y(x_section_uid, max(append_points_all[:, 1]))
    else:
        # case for 2nd quadrant
        self.xsect_coll.set_uid_base_y(x_section_uid, max(append_points_all[:, 1]))
        self.xsect_coll.set_uid_end_y(x_section_uid, min(append_points_all[:, 1]))
    self.xsect_coll.set_length(x_section_uid)
    height_buffer = (max(append_points_all[:, 2]) - min(append_points_all[:, 2])) * 0.05
    self.xsect_coll.set_uid_top(
        x_section_uid, max(append_points_all[:, 2]) + height_buffer
    )
    self.xsect_coll.set_uid_bottom(
        x_section_uid, min(append_points_all[:, 2]) - height_buffer
    )
    self.xsect_coll.set_width(x_section_uid)
    del vtkappend_all
    del append_points_all
    self.xsect_coll.set_from_table(uid=x_section_uid)


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
    # role_default  = input_combo_dialog(parent=None, title="Role", label="Default geological type", choice_list=self.geol_coll.valid_roles)
    # if not role_default :
    #     role_default  = "undef"
    # feature_from_name = options_dialog(title="Feature from name", message="Get geological feature from object name if not defined in file", yes_role="Yes", no_role="No", reject_role=None)
    # if feature_from_name == 0:
    #     feature_from_name = True
    # else:
    #     feature_from_name = False
    # Open input file
    fin = open(in_file_name, "rt")
    # Number of entities before importing________________________________
    n_entities_before = self.boundary_coll.get_number_of_entities
    # Initialize entity_counter
    entity_counter = 0
    # Parse fin file
    for line in fin:
        # Read one line from file.
        clean_line = line.strip().split()

        # The effect of the following if/elif cascade is to loop for every single object marked by
        # the GOCAD keyword, reading the lines that we want to import and skipping the others.
        if clean_line[0] == "GOCAD":
            # A new entity starts here in a GOCAD file, so here we create a new empty dictionary,
            # then we will fill its components in the next lines. Use deepcopy otherwise the
            # original dictionary would be altered.
            curr_obj_dict = deepcopy(BoundaryCollection.entity_dict)
            # curr_obj_dict['scenario'] = scenario_default

            # Store uid and topological type of new entity.
            curr_obj_dict["uid"] = str(uuid4())

            # Create the empty vtk object with class = topology.
            # if clean_line[1] == 'VSet':
            #     curr_obj_dict['topology'] = 'VertexSet'
            #     curr_obj_dict['vtk_obj'] = VertexSet()
            #     curr_obj_dict['role'] = role_default
            if clean_line[1] == "PLine":
                curr_obj_dict["topology"] = "PolyLine"
                curr_obj_dict["vtk_obj"] = PolyLine()
                # curr_obj_dict['role'] = role_default
            elif clean_line[1] == "TSurf":
                curr_obj_dict["topology"] = "TriSurf"
                curr_obj_dict["vtk_obj"] = TriSurf()
                # curr_obj_dict['role'] = role_default
            else:
                # Here topological types different from the allowed ones are handled.
                # At the moment THIS WILL CAUSE ERRORS - KEEP THIS MESSAGE JUST FOR DEBUGGING.
                # This must be reimplementende in sucha way that, is non-valid objects are found,
                # the file reader jumps to the next line starting with the 'GOCAD' keyword (if any).
                self.print_terminal("gocad2vtk - entity type not recognized ERROR.")

            # Create empty arrays for coordinates and topology and a counter for properties.
            curr_obj_points = vtkPoints()
            curr_obj_cells = vtkCellArray()
            # curr_obj_properties_collection = vtkDataArrayCollection()
            # properties_number = 0

        elif "name:" in clean_line[0]:
            if clean_line[0] == "name:":
                # standard import
                curr_obj_dict["name"] = "_".join(
                    clean_line[1:]
                )  # see if a suffix must be added to split multipart
                # if feature_from_name:
                #     curr_obj_dict['feature'] = curr_obj_dict['name']
            else:
                # solves a bug in some other software that does not add a space after name:
                curr_obj_dict["name"] = "_".join(clean_line[:])
                curr_obj_dict["name"] = curr_obj_dict["name"][
                    5:
                ]  # this removes 'name:'
                # if feature_from_name:
                #     curr_obj_dict['feature'] = curr_obj_dict['name']
            if uid_from_name:
                curr_obj_dict["uid"] = curr_obj_dict["name"]

        # elif clean_line[0] == 'GEOLOGICAL_TYPE':
        #     curr_obj_dict['role'] = ("_".join(clean_line[1:])).lower()
        #     if curr_obj_dict['role'] not in self.geol_coll.valid_roles:
        #         if "Fault" in curr_obj_dict['role']:
        #             curr_obj_dict['role'] = "fault"
        #         elif "fault" in curr_obj_dict['role']:
        #             curr_obj_dict['role'] = "fault"
        #         elif  "Horizon" in curr_obj_dict['role']:
        #             curr_obj_dict['role'] = "top"
        #         else:
        #             curr_obj_dict['role'] = "undef"
        #
        # elif clean_line[0] == 'GEOLOGICAL_FEATURE':
        #     curr_obj_dict['feature'] = ("_".join(clean_line[1:]))
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

        elif (
            clean_line[0] == "SUBVSET"
        ):  # see if and how to start a new SUBVSET part here
            pass

        elif clean_line[0] == "ILINE":  # see if and how to start a new ILINE part here
            pass

        elif clean_line[0] == "TFACE":  # see if and how to start a new TFACE part here
            pass

        elif (clean_line[0] == "VRTX") or (clean_line[0] == "PVRTX"):
            # VRTX or PVRTX is the same here since properties are not imported.
            curr_obj_points.InsertPoint(
                int(clean_line[1]) - 1,
                float(clean_line[2]),
                float(clean_line[3]),
                float(clean_line[4]),
            )  # vtkPoint with ID, X, Y Z, "-1" since first vertex has index 0 in VTK

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

        elif clean_line[0] == "ATOM":
            # NOT YET IMPLEMENTED
            # atom_id = int(clean_line[1]) - 1
            # vrtx_id = int(clean_line[2]) - 1
            pass

        elif clean_line[0] == "SEG":
            line = vtkLine()
            line.GetPointIds().SetId(
                0, int(clean_line[1]) - 1
            )  # "-1" since first vertex has index 0 in VTK
            line.GetPointIds().SetId(1, int(clean_line[2]) - 1)
            curr_obj_cells.InsertNextCell(line)

        elif clean_line[0] == "TRGL":
            triangle = vtkTriangle()
            triangle.GetPointIds().SetId(
                0, int(clean_line[1]) - 1
            )  # "-1" since first vertex has index 0 in VTK
            triangle.GetPointIds().SetId(1, int(clean_line[2]) - 1)
            triangle.GetPointIds().SetId(2, int(clean_line[3]) - 1)
            curr_obj_cells.InsertNextCell(triangle)

        elif clean_line[0] == "END":
            # When END reached, process the arrays and write the VTK entity with properties to the project geol_coll
            entity_counter += 1  # update entity counter

            # Write points and cells TO VTK OBJECT
            # if curr_obj_dict['topology'] == 'VertexSet':
            #     self.print_terminal("Importing Gocad VSet (VertexSet) as a PolyData 0D in VTK with name: " + curr_obj_dict['name'])
            #     curr_obj_dict['vtk_obj'].SetPoints(curr_obj_points)
            #     """Vertex cells, one for each point, are added here."""
            #     for pid in range(curr_obj_dict['vtk_obj'].GetNumberOfPoints()):
            #         vertex = vtkVertex()
            #         vertex.GetPointIds().SetId(0, pid)
            #         curr_obj_cells.InsertNextCell(vertex)
            #     curr_obj_dict['vtk_obj'].SetVerts(curr_obj_cells)
            #
            if curr_obj_dict["topology"] == "PolyLine":
                self.print_terminal(
                    f"Importing GOCAD PLine (PolyLine) as a PolyData 1D in VTK with name: {curr_obj_dict['name']}"
                )
                curr_obj_dict["vtk_obj"].SetPoints(curr_obj_points)
                curr_obj_dict["vtk_obj"].SetLines(curr_obj_cells)

            elif curr_obj_dict["topology"] == "TriSurf":
                self.print_terminal(
                    f"Importing GOCAD TSurf (TriSurf) as a PolyData 2D in VTK with name: {curr_obj_dict['name']}"
                )
                curr_obj_dict["vtk_obj"].SetPoints(curr_obj_points)
                curr_obj_dict["vtk_obj"].SetPolys(curr_obj_cells)

            # if properties_number > 0:
            #     for i in range(properties_number):
            #         curr_obj_dict['vtk_obj'].GetPointData().AddArray(curr_obj_properties_collection.GetItem(i))

            # Add current_entity to entities collection
            self.boundary_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
            del curr_obj_points
            del curr_obj_cells
            # del curr_obj_properties_collection
            del curr_obj_dict

            # Closing message
            self.print_terminal(f"Object n. {str(entity_counter)} saved")

    n_entities_after = self.boundary_coll.get_number_of_entities
    self.print_terminal(f"Entities before importing: {str(n_entities_before)}")
    self.print_terminal(f"Entities after importing: {str(n_entities_after)}")
    self.print_terminal(f"Entities imported: {str(entity_counter)}")


def vtk2gocad(self=None, out_file_name=None):
    """Export a GOCAD ASCII file with all the pointsets, polylines, and triangulated surfaces included, as VTK entities,
    in the self.geol_coll GeologicalCollection(), where <self> is the calling ProjectWindow() instance.
    """
    # At the moment only entities in the geological collection can be exported.
    if self.shown_table != "tabGeology":
        return
    # Open file.
    fout = open(out_file_name, "w")
    # Export selected entities.
    for uid in self.selected_uids:
        print(f"--> Exporting {uid}")
        # Loop over uids
        topology = self.geol_coll.df.loc[
            self.geol_coll.df["uid"] == uid, "topology"
        ].values[0]
        # Check if this uid is compatible with Gocad Ascii
        if topology in self.geol_coll.valid_topologies:
            # Get properties and convert to properly formatted strings
            color_R = self.geol_coll.get_uid_legend(uid=uid)["color_R"] / 255
            color_G = self.geol_coll.get_uid_legend(uid=uid)["color_G"] / 255
            color_B = self.geol_coll.get_uid_legend(uid=uid)["color_B"] / 255
            feature = self.geol_coll.df.loc[
                self.geol_coll.df["uid"] == uid, "feature"
            ].values[0]
            role = self.geol_coll.df.loc[
                self.geol_coll.df["uid"] == uid, "role"
            ].values[0]
            # time = self.a_t_df.loc[self.a_t_df["uid"] == uid, "time"].values[0]
            properties_names = self.geol_coll.df.loc[
                self.geol_coll.df["uid"] == uid, "properties_names"
            ].values[0]
            properties_components = self.geol_coll.df.loc[
                self.geol_coll.df["uid"] == uid, "properties_components"
            ].values[0]
            # Write header for each uid
            if topology in ["VertexSet", "XsVertexSet"]:
                fout.write("GOCAD VSet 1\n")
            elif topology in topology in ["PolyLine", "XsPolyLine"]:
                fout.write("GOCAD PLine 1\n")
            elif topology in ["TriSurf"]:
                fout.write("GOCAD TSurf 1\n")
            fout.write("HEADER {\n")
            fout.write(
                "*solid*color: "
                + (f"{color_R:.3f}" + " " + f"{color_G:.3f}" + " " + f"{color_B:.3f}")
                + " 1\n"
            )
            fout.write(
                "name: " + uid + "\n"
            )  # IMPORTANT: 'name' is uid, not the 'name' shown as a text label that is not unique
            fout.write("}\n")
            fout.write("GEOLOGICAL_FEATURE " + feature + "\n")
            if role in ["tectonic"]:
                # "tectonic" -> fault
                fout.write("GEOLOGICAL_TYPE fault\n")
            elif role in ["bedding", "foliation"]:
                # "bedding", "foliation" -> intraformational
                fout.write("GEOLOGICAL_TYPE intraformational\n")
            elif role in ["fault", "intrusive", "unconformity", "top"]:
                # these are the same as in GOCAD
                fout.write("GEOLOGICAL_TYPE " + role + "\n")
            elif role in ["undef", "base", "lineation", "axial_surface", "fold_axis"]:
                # these are not implemented in GOCAD
                pass
            # not yet implemented in PZero, but implemented in GOCAD: topography, boundary, ghost
            time = self.geol_coll.get_uid_legend(uid=uid)["time"]
            fout.write("STRATIGRAPHIC_POSITION " + str(time) + "\n")
            # Options for properties
            if properties_names != []:
                fout.write(
                    "PROPERTIES " + (" ".join(map(str, properties_names))) + "\n"
                )
                fout.write(
                    "ESIZES " + (" ".join(map(str, properties_components))) + "\n"
                )
                # Build PVRTX matrix here
                # _____________Check if there is an error here with vector properties_________________________________________________
                pvrtx_mtx = self.geol_coll.get_uid_vtk_obj(uid).points
                for property_name in properties_names:
                    print("property_name: ", property_name)
                    pvrtx_mtx = np_column_stack(
                        [
                            pvrtx_mtx,
                            self.geol_coll.get_uid_vtk_obj(uid).get_point_data(
                                property_name
                            ),
                        ]
                    )
            else:
                # Build VRTX matrix here
                vrtx_mtx = self.geol_coll.get_uid_vtk_obj(uid).points
            # Options for different topological types
            if topology in ["VertexSet", "XsVertexSet"]:
                fout.write("SUBVSET\n")
                # No connectivity matrix in this case.
            elif topology in ["PolyLine", "XsPolyLine"]:
                fout.write("ILINE\n")
                # ensure that PolyLine is composed of properly ordered two-node segments
                # ------------------- very slow to be solved in a different way -----------------------
                self.geol_coll.get_uid_vtk_obj(uid).sort_nodes()
                # Build connectivity matrix here.
                connectivity = self.geol_coll.get_uid_vtk_obj(uid).cells
            elif topology in ["TriSurf"]:
                fout.write("TFACE\n")
                # Build connectivity matrix here
                connectivity = self.geol_coll.get_uid_vtk_obj(uid).cells
            # elif topology in ["TetraSolid"]:
            #     fout.write("TVOLUME\n")
            #     """Build connectivity matrix here."""
            #     connectivity = self.geol_coll.get_uid_vtk_obj(uid).cells
            # Write VRTX or PVRTX
            if properties_names != []:
                for row in range(np_shape(pvrtx_mtx)[0]):
                    data_row = " ".join(
                        ["{}".format(cell) for cell in pvrtx_mtx[row, :]]
                    )
                    fout.write(
                        "PVRTX " + str(row + 1) + " " + data_row + "\n"
                    )  # row+1 since indexes in Gocad Ascii start from 1
                del pvrtx_mtx
            else:
                for row in range(np_shape(vrtx_mtx)[0]):
                    data_row = " ".join(
                        ["{}".format(cell) for cell in vrtx_mtx[row, :]]
                    )
                    fout.write(
                        "VRTX " + str(row + 1) + " " + data_row + "\n"
                    )  # row+1 since indexes in Gocad Ascii start from 1
                del vrtx_mtx
            # Write connectivity
            if topology in ["VertexSet", "XsVertexSet"]:
                pass
            elif topology in ["PolyLine", "XsPolyLine"]:
                for row in range(np_shape(connectivity)[0]):
                    data_row = " ".join(
                        ["{}".format(cell + 1) for cell in connectivity[row, :]]
                    )  # cell+1 since indexes in Gocad Ascii start from 1 - do not alter connectivity that is a shallow copy
                    fout.write("SEG " + data_row + "\n")
                del connectivity
            elif topology in ["TriSurf"]:
                for row in range(np_shape(connectivity)[0]):
                    data_row = " ".join(
                        ["{}".format(cell + 1) for cell in connectivity[row, :]]
                    )  # cell+1 since indexes in Gocad Ascii start from 1 - do not alter connectivity that is a shallow copy
                    fout.write("TRGL " + data_row + "\n")
                del connectivity
            # elif topology in ["TetraSolid"]:
            #     for row in range(np_shape(connectivity)[0]):
            #         data_row = " ".join(
            #             ["{}".format(cell + 1) for cell in connectivity[row, :]]
            #         )  # cell+1 since indexes in Gocad Ascii start from 1 - do not alter connectivity that is a shallow copy
            #         fout.write("TETRA " + data_row + "\n")
            #     del connectivity
            fout.write("END\n")
            self.print_terminal(f"Written entity {uid} to file {out_file_name}")
        else:
            self.print_terminal("Entity ", uid, "not supported in Gocad Ascii")
    fout.close()
