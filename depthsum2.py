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
            arcpy.AddMessage(str(polygon_layer))
            spacing = parameters[1].value
            azimuth = parameters[2].value
            point_interval = parameters[3].value
            avg_depth = parameters[4].value if not parameters[5].value else None
            geochem_mode = parameters[5].value

            arcpy.env.overwriteOutput = True

            # Создаём scratch.gdb рядом с .pyt, если её нет
            toolbox_folder = os.path.dirname(__file__)
            custom_scratch_gdb = os.path.join(toolbox_folder, "scratch.gdb")
            if not arcpy.Exists(custom_scratch_gdb):
                arcpy.CreateFileGDB_management(toolbox_folder, "scratch.gdb")

            arcpy.env.scratchWorkspace = custom_scratch_gdb
            scratch_gdb = arcpy.env.scratchGDB
            arcpy.AddMessage(f"Временная GDB установлена: {scratch_gdb}")

            profile_lines = os.path.join(scratch_gdb, "generated_profiles")
            collar_points = os.path.join(scratch_gdb, "generated_points")

            fishnet_fc = self.generate_profiles(polygon_layer, spacing, azimuth, profile_lines)
            self.add_layer_to_map(fishnet_fc, "Profiles")
            # self.generate_points(profile_lines, point_interval, collar_points)

            if not geochem_mode:
                self.add_depths(profile_lines, point_interval, avg_depth, "TotalMeterage",
                                os.path.join(os.path.expanduser("~"), "Desktop", "DepthLogs"))

            # self.add_layer_to_map(collar_points, "Collar Points")

            arcpy.SetParameter(0, collar_points)

        except Exception as e:
            arcpy.AddError("Execution failed: " + str(e))

    @staticmethod
    def generate_profiles(polygon_layer, spacing, azimuth, output_fc):
        try:
            desc = arcpy.Describe(polygon_layer)
            spatial_ref = desc.spatialReference

            # Определяем, нужно ли перепроецировать
            needs_projection = spatial_ref.type == "Geographic"
            arcpy.AddMessage(f"Текущая СК: {spatial_ref.name}")

            if needs_projection:
                arcpy.AddMessage("Перепроецируем полигон в WGS 1984 UTM zone 43N для расчётов в метрах.")
                projected_polygon = os.path.join(arcpy.env.scratchGDB, "projected_polygon")

                if arcpy.Exists(projected_polygon):
                    arcpy.Delete_management(projected_polygon)

                utm_sr = arcpy.SpatialReference(32643)
                arcpy.Project_management(polygon_layer, projected_polygon, utm_sr)

                arcpy.AddMessage(f"Проецируем в: {projected_polygon}")
                polygon_layer = projected_polygon  # Используем перепроецированный полигон
                spatial_ref = utm_sr  # И обновляем СК
            else:
                arcpy.AddMessage("Полигон уже в метрической СК, перепроецирование не требуется.")

            # Определяем экстент и центроид
            extent = arcpy.Describe(polygon_layer).extent
            with arcpy.da.SearchCursor(polygon_layer, ["SHAPE@"]) as cursor:
                centroid = next(cursor)[0].centroid

            width = spacing
            height = extent.height * 2

            arcpy.AddMessage(f"Fishnet height: {height}")
            arcpy.AddMessage(f"Centroid: {centroid.X}, {centroid.Y}")
            arcpy.AddMessage(f"Extent: {extent.XMin}, {extent.YMin}, {extent.XMax}, {extent.YMax}")

            raw_fishnet = os.path.join(arcpy.env.scratchGDB, "raw_fishnet")
            if arcpy.Exists(raw_fishnet):
                arcpy.Delete_management(raw_fishnet)

            origin_coord = f"{centroid.X - extent.width * 2} {centroid.Y - height / 2}"
            y_axis_coord = f"{centroid.X - extent.width * 2} {centroid.Y - height / 2 + 10}"
            corner_coord = f"{centroid.X + extent.width * 2} {centroid.Y + height / 2}"

            # Создаём fishnet
            arcpy.CreateFishnet_management(
                raw_fishnet,
                origin_coord,
                y_axis_coord,
                width,
                height,
                "0",  # rows
                "0",  # columns
                corner_coord,
                "NO_LABELS",
                None,
                "POLYLINE"
            )

            # ✅ Определяем проекцию fishnet
            arcpy.DefineProjection_management(raw_fishnet, spatial_ref)

            arcpy.AddMessage(f"Фишнет создан: {raw_fishnet}")
            return raw_fishnet

        except Exception as e:
            arcpy.AddError(f"Error generating profiles (manual rotate): {e}")

    # @staticmethod
    # def generate_points(line_layer, interval, output_fc):
    #     try:
    #         spatial_ref = arcpy.Describe(line_layer).spatialReference
    #         arcpy.CreateFeatureclass_management(
    #             out_path=os.path.dirname(output_fc),
    #             out_name=os.path.basename(output_fc),
    #             geometry_type="POINT",
    #             spatial_reference=spatial_ref
    #         )
    #         arcpy.AddField_management(output_fc, "LineID", "LONG")
    #         arcpy.AddField_management(output_fc, "PointNumber", "LONG")
    #
    #         with arcpy.da.SearchCursor(line_layer, ["OID@", "SHAPE@"]) as line_cursor, \
    #                 arcpy.da.InsertCursor(output_fc, ["SHAPE@", "LineID", "PointNumber"]) as point_cursor:
    #             for line_id, shape in line_cursor:
    #                 length = shape.length
    #                 pos = 0.0
    #                 point_num = 1
    #                 while pos < length:
    #                     point = shape.positionAlongLine(pos)
    #                     point_cursor.insertRow([point, line_id, point_num])
    #                     pos += interval
    #                     point_num += 1
    #
    #     except Exception as e:
    #         arcpy.AddError(f"Error generating points: {e}")

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