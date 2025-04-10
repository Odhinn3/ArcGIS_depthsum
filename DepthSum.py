# -*- coding: utf-8 -*-
import arcpy
import os
import datetime
import math

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

            arcpy.env.overwriteOutput = True
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            log_folder = os.path.join(desktop, "DepthLogs")
            scratch_gdb = arcpy.env.scratchGDB

            profile_lines = os.path.join(scratch_gdb, "generated_profiles")
            collar_points = os.path.join(scratch_gdb, "generated_points")

            self.generate_profiles(polygon_layer, spacing, azimuth, profile_lines)
            self.generate_points(profile_lines, point_interval, collar_points)

            if not geochem_mode:
                self.add_depths(profile_lines, point_interval, avg_depth, "TotalMeterage", log_folder)

            self.add_layer_to_map(profile_lines, "Profiles")
            self.add_layer_to_map(collar_points, "Collar Points")

            arcpy.SetParameter(0, collar_points)

        except Exception as e:
            arcpy.AddError("Execution failed: " + str(e))

    @staticmethod
    def generate_profiles(polygon_layer, spacing, azimuth, output_fc):
        try:
            desc = arcpy.Describe(polygon_layer)
            spatial_ref = desc.spatialReference

            # Если входной слой в географической СК — перепроецируем в Mercator
            if spatial_ref.type == "Geographic":
                arcpy.AddMessage("Перепроецируем полигон в WGS 1984 Web Mercator для расчётов в метрах.")
                projected_polygon = os.path.join(arcpy.env.scratchGDB, "projected_polygon")
                mercator_sr = arcpy.SpatialReference(3857)  # WGS 1984 Web Mercator Auxiliary Sphere
                arcpy.Project_management(polygon_layer, projected_polygon, mercator_sr)
                polygon_layer = projected_polygon
                spatial_ref = mercator_sr

            # Создаём временный слой с линиями
            temp_lines = os.path.join(arcpy.env.scratchGDB, "temp_lines")
            arcpy.CreateFeatureclass_management(
                out_path=os.path.dirname(temp_lines),
                out_name=os.path.basename(temp_lines),
                geometry_type="POLYLINE",
                spatial_reference=spatial_ref
            )
            arcpy.AddField_management(temp_lines, "LineID", "LONG")

            azimuth_rad = math.radians(azimuth)

            # Правильная интерпретация азимута: 0° — север, 90° — восток
            dx = math.sin(azimuth_rad)  # восточное направление
            dy = math.cos(azimuth_rad)  # северное направление
            nx = -dy  # направление смещения профилей — ортогонально (на запад)
            ny = dx

            with arcpy.da.InsertCursor(temp_lines, ["SHAPE@", "LineID"]) as insert_cursor:
                with arcpy.da.SearchCursor(polygon_layer, ["SHAPE@", "OID@"]) as search_cursor:
                    for polygon, oid in search_cursor:
                        center = polygon.centroid
                        extent = polygon.extent
                        diagonal = math.hypot(extent.width, extent.height)
                        max_offset = diagonal

                        distance = -max_offset
                        line_id = 1
                        while distance <= max_offset:
                            cx = center.X + nx * distance
                            cy = center.Y + ny * distance

                            start_point = arcpy.Point(cx - dx * 10000, cy - dy * 10000)
                            end_point = arcpy.Point(cx + dx * 10000, cy + dy * 10000)
                            line = arcpy.Polyline(arcpy.Array([start_point, end_point]), spatial_ref)

                            insert_cursor.insertRow([line, line_id])
                            line_id += 1
                            distance += spacing

            # Обрезаем профили по границе полигона
            arcpy.Clip_analysis(temp_lines, polygon_layer, output_fc)

        except Exception as e:
            arcpy.AddError(f"Error generating profiles: {e}")

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

            arcpy.AddField_management(output_fc, "LineID", "LONG")
            arcpy.AddField_management(output_fc, "PointNumber", "LONG")

            with arcpy.da.SearchCursor(line_layer, ["LineID", "SHAPE@"]) as line_cursor, \
                 arcpy.da.InsertCursor(output_fc, ["SHAPE@", "LineID", "PointNumber"]) as point_cursor:
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

        except Exception as e:
            arcpy.AddError(f"Error in add_depths: {e}")

    @staticmethod
    def add_layer_to_map(layer_path, layer_name):
        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            active_map = aprx.activeMap
            if active_map:
                active_map.addDataFromPath(layer_path)
                arcpy.AddMessage(f"Добавлен слой на карту: {layer_name}")
        except Exception as e:
            arcpy.AddWarning(f"Не удалось добавить слой {layer_name} на карту: {e}")