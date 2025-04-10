import arcpy
import os
from datetime import datetime

arcpy.env.workspace = r"D:\Temp"
arcpy.env.overwriteOutput = True

DEFAULT_DISTANCE = 100  # fallback value

#getting the backlog file on a desktop
def get_desktop_log_folder():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    log_folder = os.path.join(desktop, "depth_logs")

    if not os.path.exists(log_folder):
        os.makedirs(log_folder)
        arcpy.AddMessage(f"Created log folder: {log_folder}")
    else:
        arcpy.AddMessage(f"Using existing log folder: {log_folder}")

    return log_folder

#calculating the total depth
def depthsum(layer, distance, depth, field):
    try:
        log_folder = get_desktop_log_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(log_folder, f"depth_log_{timestamp}.txt")

        sum_depth = 0
        sum_profiles = 0

        if not arcpy.Exists(layer):
            raise ValueError("Input layer does not exist or is not accessible")

        row_count = int(arcpy.GetCount_management(layer)[0])
        if row_count == 0:
            arcpy.AddWarning("Input layer is empty. No features to process.")
            return

        with arcpy.da.UpdateCursor(layer, ["SHAPE@LENGTH", field]) as cursor, open(output_file, "w") as file:
            arcpy.AddMessage(f"Log file created: {output_file}")

            for row in cursor:
                applied_distance = distance if distance > 0 else DEFAULT_DISTANCE
                if distance <= 0:
                    arcpy.AddWarning("Distance is zero or negative — using default 100 meters.")

                line_length = row[0]
                row[1] = (round(line_length / applied_distance) + 1) * depth

                file.write(f"{round(line_length)} {row[1]}\n")

                sum_depth += row[1]
                sum_profiles += 1

                try:
                    cursor.updateRow(row)
                except Exception as update_err:
                    arcpy.AddWarning(f"Could not update row: {update_err}")

            file.write(f"Total depth: {sum_depth}\nNumber of profiles: {sum_profiles}")
            arcpy.AddMessage(f"Completed: Total depth = {sum_depth}, Profiles = {sum_profiles}")

    except Exception as e:
        arcpy.AddError(f"Error in depthsum(): {e}")


def main():
    try:
        layer = arcpy.GetParameterAsText(0)
        d = arcpy.GetParameter(1)
        a = arcpy.GetParameter(2)
        f = arcpy.GetParameterAsText(3)

        try:
            distance = int(d)
        except:
            raise ValueError("Distance must be an integer")

        try:
            depth = int(a)
        except:
            raise ValueError("Depth must be an integer")

        arcpy.AddMessage("All parameters received successfully.")

        desc = arcpy.Describe(layer)
        if desc.shapeType != "Polyline":
            raise ValueError("Input feature class must be a Polyline")

        field_names = [fld.name for fld in arcpy.ListFields(layer)]
        if f not in field_names:
            arcpy.AddMessage(f"Field '{f}' not found. Creating it...")
            arcpy.AddField_management(layer, f, "LONG")
        else:
            arcpy.AddMessage(f"Field '{f}' already exists.")

        depthsum(layer, distance, depth, f)

    except Exception as e:
        arcpy.AddError(f"Script failed: {e}")


if __name__ == "__main__":
    main()