# -*- coding: utf-8 -*-
import arcpy
import os
import datetime

class Toolbox(object):
    def __init__(self):
        self.label = "Depth Analysis Toolbox"
        self.alias = "depth_analysis"
        self.tools = [DepthTool]

class DepthTool(object):
    def __init__(self):
        self.label = "Line Depth + Point Generator"
        self.description = "Calculates depth along polylines and generates points with LineID and PointNumber"
        self.canRunInBackground = False

    def getParameterInfo(self):
        params = []

        params.append(arcpy.Parameter(
            displayName="Input Polyline Layer",
            name="in_lines",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input"
        ))
        params[0].filter.list = ["Polyline"]

        params.append(arcpy.Parameter(
            displayName="Profile Interval (meters)",
            name="profile_distance",
            datatype="Long",
            parameterType="Required",
            direction="Input"
        ))

        params.append(arcpy.Parameter(
            displayName="Depth per Profile",
            name="depth_value",
            datatype="Long",
            parameterType="Required",
            direction="Input"
        ))

        params.append(arcpy.Parameter(
            displayName="Depth Field Name",
            name="depth_field",
            datatype="String",
            parameterType="Required",
            direction="Input"
        ))

        params.append(arcpy.Parameter(
            displayName="Point Spacing (meters)",
            name="point_spacing",
            datatype="Long",
            parameterType="Required",
            direction="Input"
        ))

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        try:
            # Get parameters
            layer = parameters[0].valueAsText
            distance = int(parameters[1].value)
            depth = int(parameters[2].value)
            field = parameters[3].valueAsText
            spacing = int(parameters[4].value)

            arcpy.env.overwriteOutput = True
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            log_folder = os.path.join(desktop, "DepthLogs")

            desc = arcpy.Describe(layer)
            if desc.shapeType != "Polyline":
                raise ValueError("Input feature class must be a Polyline")

            # Add LineID field if missing
            field_names = [f.name for f in arcpy.ListFields(layer)]
            if "LineID" not in field_names:
                arcpy.AddField_management(layer, "LineID", "LONG")

            with arcpy.da.UpdateCursor(layer, ["OID@", "LineID"]) as cursor:
                for oid, _ in cursor:
                    cursor.updateRow([oid, oid])

            # Add depth field if needed
            if field not in field_names:
                arcpy.AddField_management(layer, field, "LONG")

            self.depthsum(layer, distance, depth, field, log_folder)

            # Output points to scratch GDB
            point_output_fc = os.path.join(arcpy.env.scratchGDB, "generated_points")
            self.generate_points(layer, spacing, point_output_fc)

            arcpy.AddMessage("All tasks completed successfully.")

        except Exception as e:
            arcpy.AddError("Execution failed: " + str(e))

    def depthsum(self, layer, distance, depth, field, log_folder):
        """Updates depth field based on polyline length and logs results."""
        try:
            with arcpy.da.UpdateCursor(layer, ["SHAPE@LENGTH", field]) as cursor:
                sum_depth = 0
                sum_profiles = 0

                if not os.path.isdir(log_folder):
                    os.makedirs(log_folder)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
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

                    file.write(f"Total depth: {sum_depth}\nNumber of profiles: {sum_profiles}")
                    arcpy.AddMessage(f"Total depth written to: {output_file}")

        except Exception as e:
            arcpy.AddError(f"Error in depthsum(): {e}")

    def generate_points(self, line_layer, spacing, output_fc):
        """Generates points along lines with LineID and PointNumber."""
        try:
            spatial_ref = arcpy.Describe(line_layer).spatialReference
            arcpy.CreateFeatureclass_management(
                out_path=os.path.dirname(output_fc),
                out_name=os.path.basename(output_fc),
                geometry_type="POINT",
                spatial_reference=spatial_ref
            )

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

            arcpy.AddMessage(f"Points generated and saved to: {output_fc}")

        except Exception as e:
            arcpy.AddError(f"Error generating points: {e}")