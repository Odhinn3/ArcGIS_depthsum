# -*- coding: utf-8 -*-
import arcpy
import os
import datetime
import math
from arcpy import Geometry

class Toolbox(object):
    def __init__(self):
        self.label = "Drillholes from Polygon Generator"
        self.alias = "polygon_to_profiles"
        self.tools = [PolygonToProfiles]

class PolygonToProfiles(object):
    def __init__(self):
        self.label = "Generate Profiles and Collars from Polygon"
        self.description = "Generates polylines at specified azimuth and spacing inside a polygon, then calculates total depth or generates collar points."
        self.canRunInBackground = False

    @staticmethod
    def getParameterInfo():
        params = []

        params.append(arcpy.Parameter(
            displayName="Input exploration area polygon Layer",
            name="in_polygons",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input"
        ))
        params[0].filter.list = ["Polygon"]

        params.append(arcpy.Parameter(
            displayName="Input desired profile spacing (meters)",
            name="profile_spacing",
            datatype="Long",
            parameterType="Required",
            direction="Input"
        ))

        params.append(arcpy.Parameter(
            displayName="Input desired profiles azimuth (degrees)",
            name="azimuth",
            datatype="Long",
            parameterType="Required",
            direction="Input"
        ))

        params.append(arcpy.Parameter(
            displayName="Input interval between points on profiles (meters)",
            name="point_interval",
            datatype="Long",
            parameterType="Required",
            direction="Input"
        ))

        params.append(arcpy.Parameter(
            displayName="Input expected average depth of planned drillholes (meters)",
            name="depth_value",
            datatype="Long",
            parameterType="Optional",
            direction="Input"
        ))

        params.append(arcpy.Parameter(
            displayName="Soil geochemistry mode (depths are not calculated)",
            name="geochem_mode",
            datatype="Boolean",
            parameterType="Optional",
            direction="Input"
        ))
        params[5].value = False

        params.append(arcpy.Parameter(
            displayName="UTM Zone (for example, 43 for UTM Zone 43N)",
            name="utm_zone",
            datatype="Long",
            parameterType="Required",
            direction="Input"
        ))

        return params

    @staticmethod
    def isLicensed():
        return True

    @staticmethod
    def updateParameters(parameters):
        if parameters[5].value:  # Geochem mode
            parameters[4].enabled = False
        else:
            parameters[4].enabled = True
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        try:
            polygon_layer = parameters[0].valueAsText
            spacing = parameters[1].value
            azimuth = parameters[2].value
            point_interval = parameters[3].value
            avg_depth = parameters[4].value if not parameters[5].value else None
            geochem_mode = parameters[5].value
            utm_zone = parameters[6].value

            arcpy.env.overwriteOutput = True

            toolbox_folder = os.path.dirname(__file__)
            custom_scratch_gdb = os.path.join(toolbox_folder, "scratch.gdb")
            if not arcpy.Exists(custom_scratch_gdb):
                arcpy.CreateFileGDB_management(toolbox_folder, "scratch")

            arcpy.env.scratchWorkspace = custom_scratch_gdb
            scratch_gdb = arcpy.env.scratchGDB

            profile_lines = os.path.join(scratch_gdb, "profiles")
            collar_points = os.path.join(scratch_gdb, "collars")

            fishnet_fc = self.generate_profiles(polygon_layer, spacing, azimuth, profile_lines, utm_zone)
            self.generate_points(profile_lines, point_interval, collar_points)

            self.cutting_by_polygon(polygon_layer, profile_lines, collar_points)

            if not geochem_mode:
                self.add_depths(profile_lines, point_interval, avg_depth, "TotalMeterage",
                                os.path.join(os.path.expanduser("~"), "Desktop", "DepthLogs"))

            self.add_layer_to_map(profile_lines, "profiles")
            self.add_layer_to_map(collar_points, "collars")
            arcpy.SetParameter(0, collar_points)

        except Exception as e:
            arcpy.AddError("Execution failed: " + str(e))

        try:
            for name in ["projected_polygon", "raw_fishnet", "temp_fishnet_geomfix", "rotated_fishnet", "pivot_point_fc", "generated_points"]:
                path = os.path.join(arcpy.env.scratchGDB, name)
                if arcpy.Exists(path):
                    arcpy.Delete_management(path)
                    arcpy.AddMessage(f"{name} удалён")
        except:
            arcpy.AddWarning("Temporary objects are not deleted")

    @staticmethod
    def generate_profiles(polygon_layer, spacing, azimuth, output_fc, utm_zone):
        try:
            desc = arcpy.Describe(polygon_layer)
            spatial_ref = desc.spatialReference

            needs_projection = spatial_ref.type == "Geographic"


            if needs_projection:
                epsg_code = 32600 + int(utm_zone)
                utm_sr = arcpy.SpatialReference(epsg_code)

                projected_polygon = os.path.join(arcpy.env.scratchGDB, "projected_polygon")
                if arcpy.Exists(projected_polygon):
                    arcpy.Delete_management(projected_polygon)
                arcpy.Project_management(polygon_layer, projected_polygon, utm_sr)
                polygon_layer = projected_polygon
                spatial_ref = utm_sr
            else:
                arcpy.AddMessage("Polygon reprojection is not required.")

            extent = arcpy.Describe(polygon_layer).extent
            with arcpy.da.SearchCursor(polygon_layer, ["SHAPE@"]) as cursor:
                centroid = next(cursor)[0].centroid

            width = spacing
            height = extent.height * 2

            raw_fishnet = os.path.join(arcpy.env.scratchGDB, "raw_fishnet")
            if arcpy.Exists(raw_fishnet):
                arcpy.Delete_management(raw_fishnet)

            origin_coord = f"{centroid.X - extent.width * 2} {centroid.Y - height / 2}"
            y_axis_coord = f"{centroid.X - extent.width * 2} {centroid.Y - height / 2 + 10}"
            corner_coord = f"{centroid.X + extent.width * 2} {centroid.Y + height / 2}"

            arcpy.CreateFishnet_management(
                raw_fishnet, origin_coord, y_axis_coord, width, height, "0", "0",
                corner_coord, "NO_LABELS", None, "POLYLINE"
            )

            arcpy.DefineProjection_management(raw_fishnet, spatial_ref)

            temp_fishnet = os.path.join(arcpy.env.scratchGDB, "temp_fishnet_geomfix")
            if arcpy.Exists(temp_fishnet):
                arcpy.Delete_management(temp_fishnet)
            arcpy.CopyFeatures_management(raw_fishnet, temp_fishnet)

            rotated_fishnet = os.path.join(arcpy.env.scratchGDB, "profiles")
            if arcpy.Exists(rotated_fishnet):
                arcpy.Delete_management(rotated_fishnet)

            arcpy.CreateFeatureclass_management(
                out_path=os.path.dirname(rotated_fishnet),
                out_name=os.path.basename(rotated_fishnet),
                geometry_type="POLYLINE",
                spatial_reference=spatial_ref
            )

            angle_radians = math.radians(-azimuth)
            pivot_point = arcpy.Point(centroid.X, centroid.Y)

            with arcpy.da.SearchCursor(temp_fishnet, ["SHAPE@"]) as search_cursor, \
                    arcpy.da.InsertCursor(rotated_fishnet, ["SHAPE@"]) as insert_cursor:
                for row in search_cursor:
                    geom = row[0]
                    points = [p for p in geom.getPart(0)]
                    rotated_points = []
                    for point in points:
                        dx = point.X - centroid.X
                        dy = point.Y - centroid.Y
                        new_x = centroid.X + (dx * math.cos(angle_radians) - dy * math.sin(angle_radians))
                        new_y = centroid.Y + (dx * math.sin(angle_radians) + dy * math.cos(angle_radians))
                        rotated_points.append(arcpy.Point(new_x, new_y))
                    rotated_geom = arcpy.Polyline(arcpy.Array(rotated_points))
                    insert_cursor.insertRow([rotated_geom])

            return rotated_fishnet

        except Exception as e:
            arcpy.AddError(f"Generate profiles error: {e}")

    @staticmethod
    def generate_points(line_layer, interval, output_fc):
        try:
            spatial_ref = arcpy.Describe(line_layer).spatialReference
            arcpy.CreateFeatureclass_management(
                out_path=os.path.dirname(output_fc),
                out_name=os.path.basename(output_fc),
                geometry_type="POINT",
                spatial_reference=spatial_ref
            )
            arcpy.AddField_management(output_fc, "ProfileNumber", "LONG")
            arcpy.AddField_management(output_fc, "PointNumber", "LONG")

            with arcpy.da.SearchCursor(line_layer, ["OID@", "SHAPE@"]) as line_cursor, \
                    arcpy.da.InsertCursor(output_fc, ["SHAPE@", "ProfileNumber", "PointNumber"]) as point_cursor:
                for line_id, shape in line_cursor:
                    length = shape.length
                    pos = 0.0
                    point_num = 1
                    while pos < length:
                        point = shape.positionAlongLine(pos)
                        point_cursor.insertRow([point, line_id, point_num])
                        pos += interval
                        point_num += 1

        except Exception as e:
            arcpy.AddError(f"Error generating points: {e}")

    @staticmethod
    def cutting_by_polygon(polygon_layer, line_fc, point_fc):
        try:
            clipped_lines = line_fc + "_clipped"
            clipped_points = point_fc + "_clipped"

            if arcpy.Exists(clipped_lines):
                arcpy.Delete_management(clipped_lines)
            if arcpy.Exists(clipped_points):
                arcpy.Delete_management(clipped_points)

            arcpy.Clip_analysis(line_fc, polygon_layer, clipped_lines)
            arcpy.Clip_analysis(point_fc, polygon_layer, clipped_points)

            arcpy.Delete_management(line_fc)
            arcpy.Delete_management(point_fc)
            arcpy.Rename_management(clipped_lines, line_fc)
            arcpy.Rename_management(clipped_points, point_fc)

            CuttingHelper.assign_sequential_id(line_fc, "ID")

            joined_fc = os.path.join(arcpy.env.scratchGDB, "joined_points_with_lines")
            if arcpy.Exists(joined_fc):
                arcpy.Delete_management(joined_fc)

            arcpy.SpatialJoin_analysis(
                target_features=point_fc,
                join_features=line_fc,
                out_feature_class=joined_fc,
                join_operation="JOIN_ONE_TO_ONE",
                join_type="KEEP_COMMON",
                match_option="INTERSECT"
            )

            with arcpy.da.UpdateCursor(point_fc, ["OID@", "ProfileNumber"]) as point_cursor:
                id_map = {row[0]: row[1] for row in point_cursor}

            with arcpy.da.SearchCursor(joined_fc, ["TARGET_FID", "ID"]) as join_cursor:
                update_dict = {row[0]: row[1] for row in join_cursor}

            with arcpy.da.UpdateCursor(point_fc, ["OID@", "ProfileNumber"]) as cursor:
                for row in cursor:
                    if row[0] in update_dict:
                        row[1] = update_dict[row[0]]
                        cursor.updateRow(row)

            arcpy.Delete_management(joined_fc)

            CuttingHelper.assign_sequential_id(point_fc, "PointNumber")

        except Exception as e:
            arcpy.AddError("Cutting by polygon error: " + str(e))

    @staticmethod
    def add_depths(line_layer, interval, avg_depth, field, log_folder):
        try:
            if not os.path.exists(log_folder):
                os.makedirs(log_folder)

            existing_fields = [f.name for f in arcpy.ListFields(line_layer)]
            if field not in existing_fields:
                arcpy.AddField_management(line_layer, field, "DOUBLE")

            log_file = os.path.join(log_folder, f"depth_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with arcpy.da.UpdateCursor(line_layer, ["SHAPE@LENGTH", field]) as cursor, open(log_file, "w") as file:
                total_depth = 0
                for row in cursor:
                    length = row[0]
                    n_points = int(length / interval) + 1
                    depth = n_points * avg_depth
                    row[1] = depth
                    cursor.updateRow(row)
                    total_depth += depth
                    file.write(f"{length:.2f} -> {depth}\n")
                file.write(f"Total depth: {total_depth}")
                arcpy.AddMessage(f"Total meterage of planned drilling campaign: {total_depth}")

        except Exception as e:
            arcpy.AddError(f"Error in add_depths: {e}")

    @staticmethod
    def add_layer_to_map(layer_path, layer_name):
        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            active_map = aprx.activeMap
            if active_map:
                active_map.addDataFromPath(layer_path)
        except Exception as e:
            arcpy.AddWarning(f"Layer {layer_name} was not added to map {e}")

class CuttingHelper:
    @staticmethod
    def assign_sequential_id(fc, field_name):
        # Добавить поле, если его ещё нет
        existing_fields = [f.name for f in arcpy.ListFields(fc)]
        if field_name not in existing_fields:
            arcpy.AddField_management(fc, field_name, "LONG")

        # Присвоить значения ID по порядку
        with arcpy.da.UpdateCursor(fc, [field_name]) as cursor:
            counter = 1
            for row in cursor:
                row[0] = counter
                cursor.updateRow(row)
                counter += 1