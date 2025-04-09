import arcpy, os
from DirToNewMosaic import workspace
from arcgis.geometry import lengths
from mpmath.matrices.matrices import rowsep
from numexpr.expressions import double

arcpy.env.workspace = r"D:\Temp"
arcpy.env.overwriteOutput = True

workspace = arcpy.env.workspace

def depthsum(layer, distance, depth, field, output):
    try:
        with arcpy.da.UpdateCursor(layer, ["SHAPE@LENGTH", field]) as cursor:
            sum_depth = 0
            output_file = output + ".txt"


            if os.path.isfile(output_file):
                mode = "w+"
                arcpy.AddMessage("Log file exists")
            else:
                mode = "w"
                arcpy.AddMessage("Log file is made")

            with open(output_file, mode) as file:
                for row in cursor:

                    if distance != 0:
                        row[1] = (round(row[0] / distance) + 1) * depth
                    else:

                        arcpy.AddWarning("Distance is zero, using distance 100 meters")

                        row[1] = (round(row[0] / 100) + 1) * depth

                    file.write(str(round(row[0])) + " " + str(row[1]) + "\n")
                    arcpy.AddMessage(f"New row is added: {round(row[0])} {row[1]}")

                    sum_depth += row[1]
                    arcpy.AddMessage(f"Sum is {sum_depth}")

                    cursor.updateRow(row)
                    arcpy.AddMessage("Row updated")

                file.write("Total depth: " + str(sum_depth))
                arcpy.AddMessage(f"Total depth: {sum_depth}")

    except Exception as e:
        arcpy.AddError(f"Method doesn't work: {e}")

if __name__ == "__main__":
    try:
        try:
            l = arcpy.GetParameterAsText(0)
            d = arcpy.GetParameter(1)
            isinstance(d, int)
            a = arcpy.GetParameter(2)
            isinstance(a, int)
            f = arcpy.GetParameterAsText(3)
            o = arcpy.GetParameterAsText(4)
            arcpy.AddMessage("Parameters got successfully")
        except:
            arcpy.AddError("Parameters are incorrect")

        fields = arcpy.ListFields(l)
        arcpy.AddMessage("Field list got successfully")
        field_ex = any(field.name == f for field in fields)
        arcpy.AddMessage("Field exists: " + str(field_ex))

        if field_ex:
            arcpy.AddMessage("Required field already exists")
            depthsum(l, d, a, f, o)

        else:
            arcpy.AddField_management(l, f, "LONG")
            arcpy.AddMessage("New field is added")
            depthsum(l, d, a, f, o)

    except:
        arcpy.AddError("Shit happened, see backlog")