import arcpy
import os
import datetime

arcpy.env.workspace = r"D:\Temp"
arcpy.env.overwriteOutput = True

def depthsum(layer, distance, depth, field, log_folder):
    """Updates a field with calculated depth and logs to file."""
    try:
        with arcpy.da.UpdateCursor(layer, ["SHAPE@LENGTH", field]) as cursor:
            sum_depth = 0
            sum_profiles = 0

            # Prepare log file path
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if not os.path.isdir(log_folder):
                os.makedirs(log_folder)

            output_file = os.path.join(log_folder, f"depth_log_{timestamp}.txt")
            with open(output_file, "w") as file:
                for row in cursor:
                    if distance == 0:
                        arcpy.AddWarning("Distance is zero, using default 100 meters")
                        distance = 100

                    row[1] = (round(row[0] / distance) + 1) * depth
                    file.write(f"{round(row[0])} {row[1]}\n")

                    sum_depth += row[1]
                    sum_profiles += 1
                    cursor.updateRow(row)
                    arcpy.AddMessage("Row updated")

                file.write(f"Total depth: {sum_depth}\nNumber of profiles: {sum_profiles}")
                arcpy.AddMessage(f"Total depth: {sum_depth}")

    except Exception as e:
        arcpy.AddError(f"Error in depthsum(): {e}")

def generate_points_along_lines(line_layer, spacing, output_fc):
    """Generates points along polylines with LineID and PointNumber fields."""
    try:
        arcpy.AddMessage(f"Generating points every {spacing} meters")

        spatial_ref = arcpy.Describe(line_layer).spatialReference
        arcpy.CreateFeatureclass_management(
            out_path=os.path.dirname(output_fc),
            out_name=os.path.basename(output_fc),
            geometry_type="POINT",
            spatial_reference=spatial_ref
        )

        # Add LineID and PointNumber fields
        arcpy.AddField_management(output_fc, "LineID", "LONG")
        arcpy.AddField_management(output_fc, "PointNumber", "LONG")

        with arcpy.da.SearchCursor(line_layer, ["OID@", "SHAPE@"]) as s_cursor, \
             arcpy.da.InsertCursor(output_fc, ["SHAPE@", "LineID", "PointNumber"]) as i_cursor:

            for line_id, shape in s_cursor:
                length = shape.length
                position = 0.0
                point_number = 1

                while position < length:
                    point_geom = shape.positionAlongLine(position)
                    i_cursor.insertRow([point_geom, line_id, point_number])
                    position += spacing
                    point_number += 1

        arcpy.AddMessage(f"Points with LineID and PointNumber saved to: {output_fc}")

    except Exception as e:
        arcpy.AddError(f"Error generating points: {e}")

def main():
    try:
        # Input parameters
        layer = arcpy.GetParameterAsText(0)
        distance = int(arcpy.GetParameter(1))
        depth = int(arcpy.GetParameter(2))
        field = arcpy.GetParameterAsText(3)
        spacing = int(arcpy.GetParameter(4))

        # Create log on Desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        log_folder = os.path.join(desktop, "DepthLogs")

        arcpy.AddMessage("Parameters received successfully")

        # Check geometry type
        desc = arcpy.Describe(layer)
        if desc.shapeType != "Polyline":
            arcpy.AddError("Input feature class must be a Polyline")
            raise ValueError("Invalid geometry type")

        # Add and fill LineID field
        field_names = [fld.name for fld in arcpy.ListFields(layer)]
        if "LineID" not in field_names:
            arcpy.AddField_management(layer, "LineID", "LONG")

        with arcpy.da.UpdateCursor(layer, ["OID@", "LineID"]) as cursor:
            for oid, _ in cursor:
                cursor.updateRow([oid, oid])

        # Add depth field if needed
        if field not in field_names:
            arcpy.AddField_management(layer, field, "LONG")

        # Run depthsum and generate points
        depthsum(layer, distance, depth, field, log_folder)

        point_output_fc = os.path.join(arcpy.env.workspace, "generated_points")
        generate_points_along_lines(layer, spacing, point_output_fc)

    except Exception as e:
        arcpy.AddError("Unexpected error: " + str(e))

if __name__ == "__main__":
    main()