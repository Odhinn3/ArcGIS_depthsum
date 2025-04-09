import arcpy
import os

# Настройки окружения
arcpy.env.workspace = r"D:\Temp"
arcpy.env.overwriteOutput = True


def depthsum(layer, distance, depth, field, output):
    try:
        with arcpy.da.UpdateCursor(layer, ["SHAPE@LENGTH", field]) as cursor:
            sum_depth = 0
            output_file = output + ".txt"

            mode = "w+" if os.path.isfile(output_file) else "w"
            arcpy.AddMessage("Log file exists" if mode == "w+" else "Log file is made")

            with open(output_file, mode) as file:
                for row in cursor:
                    if distance == 0:
                        arcpy.AddWarning("Distance is zero, using default 100 meters")
                        distance = 100

                    row[1] = (round(row[0] / distance) + 1) * depth
                    file.write(f"{round(row[0])} {row[1]}\n")
                    arcpy.AddMessage(f"New row added: {round(row[0])} {row[1]}")

                    sum_depth += row[1]
                    arcpy.AddMessage(f"Sum so far: {sum_depth}")

                    cursor.updateRow(row)
                    arcpy.AddMessage("Row updated")

                file.write(f"Total depth: {sum_depth}")
                arcpy.AddMessage(f"Total depth: {sum_depth}")

    except Exception as e:
        arcpy.AddError(f"Error in depthsum: {e}")


def main():
    try:
        # Получение параметров
        l = arcpy.GetParameterAsText(0)
        d = int(arcpy.GetParameter(1))
        a = int(arcpy.GetParameter(2))
        f = arcpy.GetParameterAsText(3)
        o = arcpy.GetParameterAsText(4)

        arcpy.AddMessage("Parameters received successfully")

        # Проверка на тип слоя
        desc = arcpy.Describe(l)
        if desc.shapeType != "Polyline":
            arcpy.AddError("Input feature class must be a Polyline")
            raise ValueError("Invalid geometry type")

        # Проверка наличия поля
        fields = arcpy.ListFields(l)
        field_exists = any(field.name == f for field in fields)
        arcpy.AddMessage("Field exists: " + str(field_exists))

        if not field_exists:
            arcpy.AddField_management(l, f, "LONG")
            arcpy.AddMessage("Field created")

        # Основной расчет
        depthsum(l, d, a, f, o)

    except Exception as e:
        arcpy.AddError("Unexpected error: " + str(e))


if __name__ == "__main__":
    main()
