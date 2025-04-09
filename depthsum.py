import arcpy, os
from DirToNewMosaic import workspace
from arcgis.geometry import lengths
from mpmath.matrices.matrices import rowsep

arcpy.env.workspace = r"D:\Temp"
arcpy.env.overwriteOutput = True

workspace = arcpy.env.workspace

def depthsum(layer, distance, depth, output):
    try:
        with arcpy.da.UpdateCursor(layer, ["SHAPE@LENGTH", "DHMeterage"]) as cursor:
            file = ""
            if os.path.isfile(o + ".txt"):
                with open("D:/log.txt", "w+") as file:
                    for row in cursor:
                        row[1] = (round(row[0] / distance) + 1) * depth
                        file.write(str(round(row[0])) + " " + str(row[1]) + "\n")
                        cursor.updateRow(row)
                    print("File is exist")
            else:
                with open(o + ".txt", "w") as file:
                    for row in cursor:
                        row[1] = (round(row[0] / distance) + 1) * depth
                        file.write(str(round(row[0])) + " " + str(row[1]) + "\n")
                        cursor.updateRow(row)
                    print("New file is made")
    except:
        print("What a fuck is goin` on?")


if __name__ == "__main__":

    l = arcpy.GetParameterAsText(0)
    d = arcpy.GetParameter(1)
    a = arcpy.GetParameter(2)
    o = arcpy.GetParameterAsText(3)

    depthsum(l, d, a, o)