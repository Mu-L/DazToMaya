import os, sys

import pymel.core as pm
import maya.cmds  as cmds

from Definitions import EXPORT_DIR
from DtuLoader import DtuLoader
from TextureLib import texture_library, texture_maps



class DazMaterials:
    material_dict = {}
    keep_phong = False

    def __init__(self, keep_phong):
        self.keep_phong = keep_phong

    def convert_color(self, color):
        '''Takes a hex rgb string (e.g. #ffffff) and returns an RGB tuple (float, float, float).'''
        return tuple(int(color[i:i + 2], 16) / 255. for i in (1, 3, 5)) # skip '#'

    def load_materials(self):
        """
        Load materials from Dtu file
        """
        dtu_path = os.path.abspath(EXPORT_DIR + "/FIG/FIG0")
        dtu_loader = DtuLoader(dtu_path)
        mats = dtu_loader.get_materials_list()
        for mat in mats:
            asset_name = mat["Asset Name"]
            asset_name = asset_name.replace(" ", "_")
            mat_name = mat["Material Name"].replace(" ", "_")
            if asset_name not in self.material_dict.keys():
                self.material_dict[asset_name] = {}
            self.material_dict[asset_name][mat_name] = mat

    def get_materials_in_scene(self):
        # No need to pass in a string to `type`, if you don't want to.
        for shading_engine in pm.ls(type=pm.nt.ShadingEngine):
            # ShadingEngines are collections, so you can check against their length
            if len(shading_engine):
                # You can call listConnections directly on the attribute you're looking for.
                for material in shading_engine.surfaceShader.listConnections():
                    yield material

    def find_mat_properties(self, obj, mat):
        if obj not in self.material_dict.keys():
            return
        if mat not in self.material_dict[obj].keys():
            alt_mat = mat.split("_")[0]
            if alt_mat not in self.material_dict[obj].keys():
                return
            print("WARNING: Unable to find material: " + str(mat) + " in object: " + str(obj) + ", using: " + str(alt_mat))
            mat = alt_mat
        properties = {}
        for prop in self.material_dict[obj][mat]["Properties"]:
            if "Texture" in prop.keys():
                if (not os.path.isabs(prop["Texture"])) and (prop["Texture"] != ""):
                    prop["Texture"] = os.path.join(EXPORT_DIR, prop["Texture"])
            properties[prop["Name"]] = prop
        return properties

    """
    Reference for the standard followed.
    https://substance3d.adobe.com/tutorials/courses/Substance-guide-to-Rendering-in-Arnold
    """
    
    
    def convert_to_arnold(self):
        allshaders = self.get_materials_in_scene()
        self.load_materials()
        
        for shader in allshaders:
            #print("DEBUG: convert_to_arnold(): shader=" + str(shader) )
            # get shading engine
            se = shader.shadingGroups()[0]
            shader_connections = shader.listConnections()
            # get assigned shapes
            members = se.members()
            
            if len(members) > 0:
                split = members[0].split("Shape")
                if len(split) > 1:
                    obj_name = split[0]
                    props = self.find_mat_properties(obj_name, shader.name())
                    #print("    - obj_name=" + str(obj_name) + ", shader.name()=" + str(shader.name()) + ", props=" + str(props) )

                    if props:
                        # create shader and connect shader
                        surface = pm.shadingNode("aiStandardSurface", n = shader.name() + "_ai", asShader = True)
                        #print("    - surface=" + str(surface) )
                        
                        # set material to shader
                        surface.outColor >> se.aiSurfaceShader
                        if not self.keep_phong:
                            surface.outColor >> se.surfaceShader
                        surface.base.set(1)

                        avail_tex = {}
                        for tex_type in texture_library.keys():
                            for tex_name in texture_library[tex_type]["Name"]:
                                if tex_name in props.keys():
                                    if tex_type in avail_tex.keys():
                                        if props[tex_name]["Texture"] == "":
                                            continue
                                    avail_tex[tex_type] = tex_name

                        blend_color_node = None
                        clr_node = None
                        if "makeup-weight" in avail_tex.keys() and "makeup-base" in avail_tex.keys() and "color" in avail_tex.keys():
                            makeup_weight = avail_tex["makeup-weight"]
                            makeup_base = avail_tex["makeup-base"]
                            skin_color = avail_tex["color"]
                            if props[makeup_weight]["Texture"] != "" and props[makeup_base]["Texture"] != "" and props[skin_color]["Texture"] != "":
                                # create blend color
                                blend_color_node = pm.shadingNode("blendColors", n = "makeup_blend", asUtility = True)
                                blend_color_node.output >> surface.baseColor
                                blend_color_node.output >> shader.color
                                # weight
                                weight_node = pm.shadingNode("file", n=makeup_weight, asTexture = True)
                                weight_node.setAttr('fileTextureName', props[makeup_weight]["Texture"])
                                scalar = float(props[makeup_weight]["Value"])
                                weight_node.setAttr('colorGain', [scalar, scalar, scalar])
                                weight_node.setAttr('colorSpace', 'Raw', type='string')
                                rgb_to_hsv_node = pm.shadingNode("rgbToHsv", n = "rgbToHsv", asUtility = True)
                                weight_node.outColor >> rgb_to_hsv_node.inRgb
                                rgb_to_hsv_node.outHsvV >> blend_color_node.blender
                                # makeup base
                                base_node = pm.shadingNode("file", n=makeup_base, asTexture = True)
                                base_node.setAttr('fileTextureName', props[makeup_base]["Texture"])
                                color_as_vector = self.convert_color(props[makeup_base]["Value"])
                                base_node.setAttr('colorGain', color_as_vector)
                                base_node.outColor >> blend_color_node.color1
                                # skin color
                                skin_node = pm.shadingNode("file", n = skin_color, asTexture = True)
                                skin_node.setAttr('fileTextureName',props[skin_color]["Texture"])
                                color_as_vector = self.convert_color(props[skin_color]["Value"])
                                skin_node.setAttr('colorGain', color_as_vector)
                                skin_node.outColor >> blend_color_node.color2

                        if "color" in avail_tex.keys() and blend_color_node is None:
                            prop = avail_tex["color"]
                            if props[prop]["Texture"] != "":
                                clr_node = pm.shadingNode("file", n = prop, asTexture = True)
                                clr_node.setAttr('fileTextureName',props[prop]["Texture"])
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                clr_node.setAttr('colorGain', color_as_vector)
                                clr_node.outColor >> surface.baseColor
                            else:
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                surface.setAttr('baseColor', color_as_vector)
                        
                        if "opacity" in avail_tex.keys():
                            prop = avail_tex["opacity"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName',props[prop]["Texture"])
                                scalar = float(props[prop]["Value"])
                                file_node.setAttr('colorGain', [scalar, scalar, scalar])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outColor >> surface.opacity
                                cmds.setAttr('hardwareRenderingGlobals.transparencyAlgorithm', 5)

                        if "transparency" in avail_tex.keys():
                            prop = avail_tex["transparency"]
                            surface.setAttr('transmission', props[prop]["Value"])
                            color_as_vector = self.convert_color(props[avail_tex["color"]]["Value"])
                            surface.setAttr('transmissionColor', color_as_vector)

                        if "ior" in avail_tex.keys():
                            prop = avail_tex["ior"]
                            surface.setAttr('specularIOR', props[prop]["Value"])                            

                        if "metalness" in avail_tex.keys():
                            prop = avail_tex["metalness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outAlpha >> surface.metalness
                        
                        if "roughness" in avail_tex.keys():
                            prop = avail_tex["roughness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outAlpha >> surface.specularRoughness
                            else:
                                surface.setAttr('specularRoughness', props[prop]["Value"])

                        if "specular" in avail_tex.keys():
                            prop = avail_tex["specular"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"]) 
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outColor >> surface.specularColor

                        if "normal" in avail_tex.keys():
                            prop = avail_tex["normal"]
                            if props[prop]["Texture"] != "":
                                normal_map = pm.shadingNode("aiNormalMap", asUtility = True)
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.outColor >> normal_map.input
                                normal_strength = props[prop]["Value"]
                                # detect if normal_strength is a hexadecimal string and convert to float
                                if type(normal_strength) == str:
                                    try:
                                        normal_strength = self.convert_color(normal_strength)[0]
                                    except Exception as e:
                                        print("Error: convert_to_arnold(): Error processing normal map: " + str(e) + ", setting normal_strength to 1.0")
                                        normal_strength = 1.0
                                if float(normal_strength) < 0:
                                   normal_map.setAttr('strength', (-1* float(normal_strength))) 
                                   normal_map.setAttr('invertY', 1)
                                else:
                                    normal_map.setAttr('strength', float(normal_strength))
                                normal_map.outValue >> surface.normalCamera             

                        if "bump" in avail_tex.keys():
                            prop = avail_tex["bump"]
                            if props[prop]["Texture"] != "":
                                bump_node = pm.shadingNode("aiBump2d", asUtility = True)
                                file_node = pm.shadingNode("file", n = shader.name() + "_" + prop + "_tx", asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outAlpha >> bump_node.bumpMap
                                if "normal" in avail_tex.keys():
                                    if props[avail_tex["normal"]]["Texture"] != "":
                                        normal_map.outValue >> bump_node.normal
                                bump_node.outValue >> surface.normalCamera           
                        
                        if "detail-mask" in avail_tex.keys():
                            uv_tile = pm.shadingNode("place2dTexture", asUtility = True)
                            uv_tile.setAttr('repeatU', props["Detail Horizontal Tiles"]['Value'])
                            uv_tile.setAttr('repeatV', props["Detail Vertical Tiles"]['Value'])

                            detail_normal_map = pm.shadingNode("aiNormalMap", asUtility = True)
                            nrm_node = pm.shadingNode("file", n = shader.name() + "_detail_nrm_tx", asTexture = True)
                            nrm_node.setAttr('fileTextureName', props[avail_tex['detail-normal']]["Texture"])
                            nrm_node.setAttr('colorSpace', 'Raw', type='string')
                            nrm_node.outColor >> detail_normal_map.input
                            uv_tile.outUV >> nrm_node.uvCoord

                            rgh_node = pm.shadingNode("file", n = shader.name() + "_detail_rough_tx", asTexture = True)
                            rgh_node.setAttr('fileTextureName', props[avail_tex['detail-roughness']]["Texture"])
                            rgh_node.setAttr('colorSpace', 'Raw', type='string')
                            rgh_node.setAttr('alphaIsLuminance', True)
                            uv_tile.outUV >> rgh_node.uvCoord
                            
                            detail = pm.shadingNode("aiStandardSurface", n = shader.name() + "_detail_ai", asShader = True)
                            detail.base.set(1)
                            if clr_node:
                                clr_node.outColor >> detail.baseColor
                            elif blend_color_node:
                                blend_color_node.output >> detail.baseColor
                            normal_map.outValue >> detail.normalCamera 
                            rgh_node.outAlpha >> detail.specularRoughness

                            mix = pm.shadingNode("aiMixShader", n = shader.name() + "_mix_ai", asShader = True)
                            surface.outColor >> mix.shader1
                            detail.outColor >> mix.shader2
                            mix.setAttr('mode', 1)

                            if props[avail_tex['detail-mask']]["Texture"] != "":
                                msk_node = pm.shadingNode("file", asTexture = True)
                                msk_node.setAttr('fileTextureName', props[avail_tex['detail-mask']]["Texture"])
                                msk_node.setAttr('colorSpace', 'Raw', type='string')
                                msk_node.setAttr('alphaIsLuminance', True)
                                msk_node.setAttr('invert', 1)
                                msk_node.outAlpha >> mix.mix
                            else:
                                mix.setAttr('mix', props[avail_tex['detail-mask']]['Value'])

                            mix.outColor >> se.aiSurfaceShader

                        if "sss-radius" in avail_tex.keys():
                            if props[avail_tex["color"]]["Texture"] != "":
                                if clr_node:
                                    clr_node.outColor >> surface.subsurfaceColor
                                elif blend_color_node:
                                    blend_color_node.output >> surface.subsurfaceColor
                                if "detail-mask" in avail_tex.keys():
                                    if clr_node:
                                        clr_node.outColor >> detail.subsurfaceColor
                                    elif blend_color_node:
                                        blend_color_node.output >> detail.subsurfaceColor
                            else:
                                color_as_vector = self.convert_color(props[avail_tex["color"]]["Value"])
                                surface.setAttr("subsurfaceColor", color_as_vector)
                                if "detail-mask" in avail_tex.keys():
                                    detail.setAttr("subsurfaceColor", color_as_vector)
                            
                            radius_as_vector = self.convert_color(props[avail_tex["sss-radius"]]["Value"])
    
                            surface.base.set(0)
                            surface.setAttr("subsurface", 1)
                            surface.setAttr("subsurfaceRadius", radius_as_vector)
                            surface.setAttr("subsurfaceScale", 0.5)
                            if "detail-mask" in avail_tex.keys():
                                detail.base.set(0)
                                detail.setAttr("subsurface", 1)
                                detail.setAttr("subsurfaceRadius", radius_as_vector)
                                detail.setAttr("subsurfaceScale", 0.5)

                        if not self.keep_phong:
                            pm.delete(shader)

        #print("DEBUG: convert_to_arnold(): done")
        return


    ## DB 2023-July-17: find if any HD makeup properties are present
    def has_hd_makeup(self):
        self.load_materials()
        for obj in self.material_dict.keys():
            # print("DEBUG: HD Makeup check, obj=" + str(obj) )
            for mat in self.material_dict[obj].keys():
                # print("DEBUG: HD Makeup check, mat=" + str(mat) )
                for prop in self.material_dict[obj][mat]["Properties"]:
                    # print("DEBUG: HD Makeup check, prop=" + prop["Name"])
                    if "Name" in prop.keys() and prop["Name"] == "Makeup Enable":
                        if "Value" in prop.keys() and prop["Value"] == 1:
                            #print("DEBUG: HD Makeup found")
                            return True
        return False


    ## DB 2023-July-17: safe shader update which will not break Maya's Fbx Exporter
    def update_phong_shaders_safe(self):
        allshaders = self.get_materials_in_scene()
        self.load_materials()
        
        for shader in allshaders:
            # get shading engine
            se = shader.shadingGroups()[0]
            shader_connections = shader.listConnections()
            # get assigned shapes
            members = se.members()
            
            if len(members) > 0:
                split = members[0].split("Shape")
                if len(split) > 1:
                    obj_name = split[0]
                    props = self.find_mat_properties(obj_name, shader.name())
                    
                    if props:

                        avail_tex = {}
                        for tex_type in texture_library.keys():
                            for tex_name in texture_library[tex_type]["Name"]:
                                if tex_name in props.keys():
                                    if tex_type in avail_tex.keys():
                                        if props[tex_name]["Texture"] == "":
                                            continue
                                    avail_tex[tex_type] = tex_name

                        blend_color_node = None
                        clr_node = None
                        file_node = None

                        if "color" in avail_tex.keys() and blend_color_node is None:
                            prop = avail_tex["color"]
                            if props[prop]["Texture"] != "":
                                clr_node = pm.shadingNode("file", n = prop, asTexture = True)
                                clr_node.setAttr('fileTextureName',props[prop]["Texture"])
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                clr_node.setAttr('colorGain', color_as_vector)
                                clr_node.outColor >> shader.color
                            else:
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                shader.setAttr('color', color_as_vector)

                        if "opacity" in avail_tex.keys():
                            prop = avail_tex["opacity"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName',props[prop]["Texture"])
                                scalar = float(props[prop]["Value"])
                                file_node.setAttr('alphaGain', scalar)
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outTransparency >> shader.transparency

                        # if "transparency" in avail_tex.keys():
                        #     prop = avail_tex["transparency"]
                        #     shader.setAttr('transmission', props[prop]["Value"])
                        #     color_as_vector = self.convert_color(props[avail_tex["color"]]["Value"])
                        #     shader.setAttr('transmissionColor', color_as_vector)

                        if "roughness" in avail_tex.keys():
                            prop = avail_tex["roughness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                scalar = float(props[prop]["Value"])
                                file_node.setAttr('alphaGain', scalar)
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.setAttr('invert', True)
                                file_node.outAlpha >> shader.cosinePower
                            else:
                                print("DEBUG: update_phong_shaders_safe(): no roughness image file, using roughness_val=" + str(props[prop]["Value"]) + ", for material: " + str(shader.name()))
                                roughness_val = props[prop]["Value"]
                                cosinePower_val = (1.0 - roughness_val)*100.0
                                cosinePower_val = max(cosinePower_val, 2.0)
                                cosinePower_val = min(cosinePower_val, 100.0)
                                shader.setAttr('cosinePower', cosinePower_val)

                        if "normal" in avail_tex.keys():
                            prop = avail_tex["normal"]
                            if props[prop]["Texture"] != "":
                                bump_node = pm.shadingNode("bump2d", asUtility=True)
                                bump_node.bumpInterp.set(1)  # 1 = Tangent Space Normals
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.outAlpha >> bump_node.bumpValue  # Use outAlpha for normal maps
                                normal_strength = props[prop]["Value"]
                                # Adjust bump depth
                                if isinstance(normal_strength, str):
                                    try:
                                        normal_strength = self.convert_color(normal_strength)[0]
                                    except Exception as e:
                                        print("Error: update_phong_shaders_safe(): Error processing normal map: " + str(e) + ", setting normal_strength to 1.0")
                                        normal_strength = 1.0
                                bump_node.bumpDepth.set(float(normal_strength))
                                bump_node.outNormal >> shader.normalCamera

                        if "metalness" in avail_tex.keys():
                            prop = avail_tex["metalness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                scalar = float(props[prop]["Value"])
                                file_node.setAttr('alphaGain', scalar)
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outAlpha >> shader.reflectivity
                            else:
                                shader.setAttr('reflectivity', props[prop]["Value"])

                        # if "specular" in avail_tex.keys():
                        #     prop = avail_tex["specular"]
                        #     if props[prop]["Texture"] != "":
                        #         file_node = pm.shadingNode("file", n = prop, asTexture = True)
                        #         file_node.setAttr('fileTextureName', props[prop]["Texture"]) 
                        #         file_node.setAttr('colorSpace', 'Raw', type='string')
                        #         file_node.setAttr('alphaIsLuminance', True)
                        #         file_node.outColor >> shader.specularColor


    ## DB 2023-July-17: enhanced shader update which may break Maya's Fbx Exporter
    def update_phong_shaders_with_makeup(self):
        allshaders = self.get_materials_in_scene()
        self.load_materials()
        
        for shader in allshaders:
            # get shading engine
            se = shader.shadingGroups()[0]
            shader_connections = shader.listConnections()
            # get assigned shapes
            members = se.members()
            
            if len(members) > 0:
                split = members[0].split("Shape")
                if len(split) > 1:
                    obj_name = split[0]
                    props = self.find_mat_properties(obj_name, shader.name())
                    
                    if props:

                        avail_tex = {}
                        for tex_type in texture_library.keys():
                            for tex_name in texture_library[tex_type]["Name"]:
                                if tex_name in props.keys():
                                    if tex_type in avail_tex.keys():
                                        if props[tex_name]["Texture"] == "":
                                            continue
                                    avail_tex[tex_type] = tex_name

                        blend_color_node = None
                        clr_node = None
                        if "makeup-weight" in avail_tex.keys() and "makeup-base" in avail_tex.keys() and "color" in avail_tex.keys():
                            makeup_weight = avail_tex["makeup-weight"]
                            makeup_base = avail_tex["makeup-base"]
                            skin_color = avail_tex["color"]
                            if props[makeup_weight]["Texture"] != "" and props[makeup_base]["Texture"] != "" and props[skin_color]["Texture"] != "":
                                # create blend color
                                blend_color_node = pm.shadingNode("blendColors", n = "makeup_blend", asUtility = True)
                                blend_color_node.output >> shader.color
                                # weight
                                weight_node = pm.shadingNode("file", n=makeup_weight, asTexture = True)
                                weight_node.setAttr('fileTextureName', props[makeup_weight]["Texture"])
                                scalar = float(props[makeup_weight]["Value"])
                                weight_node.setAttr('colorGain', [scalar, scalar, scalar])
                                weight_node.setAttr('colorSpace', 'Raw', type='string')
                                rgb_to_hsv_node = pm.shadingNode("rgbToHsv", n = "rgbToHsv", asUtility = True)
                                weight_node.outColor >> rgb_to_hsv_node.inRgb
                                rgb_to_hsv_node.outHsvV >> blend_color_node.blender
                                # makeup base
                                base_node = pm.shadingNode("file", n=makeup_base, asTexture = True)
                                base_node.setAttr('fileTextureName', props[makeup_base]["Texture"])
                                color_as_vector = self.convert_color(props[makeup_base]["Value"])
                                base_node.setAttr('colorGain', color_as_vector)
                                base_node.outColor >> blend_color_node.color1
                                # skin color
                                skin_node = pm.shadingNode("file", n = skin_color, asTexture = True)
                                skin_node.setAttr('fileTextureName',props[skin_color]["Texture"])
                                color_as_vector = self.convert_color(props[skin_color]["Value"])
                                skin_node.setAttr('colorGain', color_as_vector)
                                skin_node.outColor >> blend_color_node.color2

                        if "color" in avail_tex.keys() and blend_color_node is None:
                            prop = avail_tex["color"]
                            if props[prop]["Texture"] != "":
                                clr_node = pm.shadingNode("file", n = prop, asTexture = True)
                                clr_node.setAttr('fileTextureName',props[prop]["Texture"])
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                clr_node.setAttr('colorGain', color_as_vector)
                                clr_node.outColor >> shader.color
                            else:
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                shader.setAttr('color', color_as_vector)

                        if "opacity" in avail_tex.keys():
                            prop = avail_tex["opacity"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName',props[prop]["Texture"])
                                scalar = float(props[prop]["Value"])
                                file_node.setAttr('alphaGain', scalar)
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outTransparency >> shader.transparency

                        if "roughness" in avail_tex.keys():
                            prop = avail_tex["roughness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                scalar = float(props[prop]["Value"])
                                file_node.setAttr('alphaGain', scalar)
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.setAttr('invert', True)
                                file_node.outAlpha >> shader.cosinePower
                            else:
                                roughness_val = props[prop]["Value"]
                                cosinePower_val = (1.0 - roughness_val)*100.0
                                cosinePower_val = max(cosinePower_val, 2.0)
                                cosinePower_val = min(cosinePower_val, 100.0)
                                shader.setAttr('cosinePower', cosinePower_val)

                        if "normal" in avail_tex.keys():
                            prop = avail_tex["normal"]
                            if props[prop]["Texture"] != "":
                                bump_node = pm.shadingNode("bump2d", asUtility=True)
                                bump_node.bumpInterp.set(1)  # 1 = Tangent Space Normals
                                file_node = pm.shadingNode("file", n = prop, asTexture = True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.outAlpha >> bump_node.bumpValue  # Use outAlpha for normal maps
                                normal_strength = props[prop]["Value"]
                                # Adjust bump depth
                                if isinstance(normal_strength, str):
                                    try:
                                        normal_strength = self.convert_color(normal_strength)[0]
                                    except Exception as e:
                                        print("Error: update_phong_shaders_with_makeup(): Error processing normal map: " + str(e) + ", setting normal_strength to 1.0")
                                        normal_strength = 1.0
                                bump_node.bumpDepth.set(float(normal_strength))
                                bump_node.outNormal >> shader.normalCamera

                        if "metalness" in avail_tex.keys():
                            prop = avail_tex["metalness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                scalar = float(props[prop]["Value"])
                                file_node.setAttr('alphaGain', scalar)
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outAlpha >> shader.reflectivity
                            else:
                                shader.setAttr('reflectivity', props[prop]["Value"])

                        # if "transparency" in avail_tex.keys():
                        #     prop = avail_tex["transparency"]
                        #     shader.setAttr('transmission', props[prop]["Value"])
                        #     color_as_vector = self.convert_color(props[avail_tex["color"]]["Value"])
                        #     shader.setAttr('transmissionColor', color_as_vector)

                        # if "roughness" in avail_tex.keys():
                        #     prop = avail_tex["roughness"]
                        #     if props[prop]["Texture"] != "":
                        #         file_node = pm.shadingNode("file", n = prop, asTexture = True)
                        #         file_node.setAttr('fileTextureName', props[prop]["Texture"])
                        #         scalar = float(props[prop]["Value"])
                        #         file_node.setAttr('alphaGain', scalar)
                        #         file_node.setAttr('colorSpace', 'Raw', type='string')
                        #         file_node.setAttr('alphaIsLuminance', True)
                        #         file_node.setAttr('invert', True)
                        #         multiply100 = pm.shadingNode("floatMath", asUtility = True)
                        #         multiply100.setAttr('operation', 2) # add=0, subtract, multiply, divide, min, max, power
                        #         multiply100.setAttr('floatB', 100.0)
                        #         file_node.outAlpha >> multiply100.floatA
                        #         clamp = pm.shadingNode("clamp", asUtility = True)
                        #         clamp.setAttr('min', [2.0, 2.0, 2.0])
                        #         clamp.setAttr('max', [100.0, 100.0, 100.0])
                        #         multiply100.outFloat >> clamp.inputR
                        #         clamp.outputR >> shader.cosinePower
                        #     else:
                        #         roughness_val = props[prop]["Value"]
                        #         cosinePower_val = (1.0 - roughness_val)*100.0
                        #         cosinePower_val = max(cosinePower_val, 2.0)
                        #         cosinePower_val = min(cosinePower_val, 100.0)
                        #         shader.setAttr('cosinePower', cosinePower_val)

                        # if "normal" in avail_tex.keys():
                        #     prop = avail_tex["normal"]
                        #     if props[prop]["Texture"] != "":
                        #         normal_map = pm.shadingNode("aiNormalMap", asUtility = True)
                        #         file_node = pm.shadingNode("file", n = prop, asTexture = True)
                        #         file_node.setAttr('fileTextureName', props[prop]["Texture"])
                        #         file_node.setAttr('colorSpace', 'Raw', type='string')
                        #         file_node.outColor >> normal_map.input
                        #         if float(props[prop]["Value"]) < 0:
                        #            normal_map.setAttr('strength', (-1* float(props[prop]["Value"]))) 
                        #            normal_map.setAttr('invertY', 1)
                        #         else:
                        #             normal_map.setAttr('strength', float(props[prop]["Value"]))
                        #         normal_map.outValue >> shader.normalCamera

                        # if "bump" in avail_tex.keys():
                        #     prop = avail_tex["bump"]
                        #     if props[prop]["Texture"] != "":
                        #         bump_node = pm.shadingNode("aiBump2d", asUtility = True)
                        #         file_node = pm.shadingNode("file", n = shader.name() + "_" + prop + "_tx", asTexture = True)
                        #         file_node.setAttr('fileTextureName', props[prop]["Texture"])
                        #         file_node.setAttr('colorSpace', 'Raw', type='string')
                        #         file_node.setAttr('alphaIsLuminance', True)
                        #         file_node.outAlpha >> bump_node.bumpMap
                        #         # if "normal" in avail_tex.keys():
                        #         #     if props[avail_tex["normal"]]["Texture"] != "":
                        #         #         normal_map.outValue >> bump_node.normal
                        #         bump_node.outValue >> shader.normalCamera

                        # if "specular" in avail_tex.keys():
                        #     prop = avail_tex["specular"]
                        #     if props[prop]["Texture"] != "":
                        #         file_node = pm.shadingNode("file", n = prop, asTexture = True)
                        #         file_node.setAttr('fileTextureName', props[prop]["Texture"]) 
                        #         file_node.setAttr('colorSpace', 'Raw', type='string')
                        #         file_node.setAttr('alphaIsLuminance', True)
                        #         file_node.outColor >> shader.specularColor
        return

    ## DB 2024-09-18: standard surface shader implementation
    def convert_to_standard_surface(self):
        allshaders = self.get_materials_in_scene()
        self.load_materials()
        
        for shader in allshaders:
            # get shading engine
            se = shader.shadingGroups()[0]
            shader_connections = shader.listConnections()
            # get assigned shapes
            members = se.members()
            
            if len(members) > 0:
                split = members[0].split("Shape")
                if len(split) > 1:
                    obj_name = split[0]
                    props = self.find_mat_properties(obj_name, shader.name())

                    if props:
                        # Create Standard Surface shader and connect to shading group
                        surface = pm.shadingNode("standardSurface", n=shader.name() + "_std", asShader=True)
                        
                        # Connect the shader to the shading group
                        surface.outColor >> se.surfaceShader
                        surface.base.set(1)
                        
                        avail_tex = {}
                        for tex_type in texture_library.keys():
                            for tex_name in texture_library[tex_type]["Name"]:
                                if tex_name in props.keys():
                                    if tex_type in avail_tex.keys():
                                        if props[tex_name]["Texture"] == "":
                                            continue
                                    avail_tex[tex_type] = tex_name

                        blend_color_node = None
                        clr_node = None
                        if "makeup-weight" in avail_tex.keys() and "makeup-base" in avail_tex.keys() and "color" in avail_tex.keys():
                            makeup_weight = avail_tex["makeup-weight"]
                            makeup_base = avail_tex["makeup-base"]
                            skin_color = avail_tex["color"]
                            if props[makeup_weight]["Texture"] != "" and props[makeup_base]["Texture"] != "" and props[skin_color]["Texture"] != "":
                                # Create blend color
                                blend_color_node = pm.shadingNode("blendColors", n="makeup_blend", asUtility=True)
                                blend_color_node.output >> surface.baseColor
                                # Weight
                                weight_node = pm.shadingNode("file", n=makeup_weight, asTexture=True)
                                weight_node.setAttr('fileTextureName', props[makeup_weight]["Texture"])
                                scalar = float(props[makeup_weight]["Value"])
                                weight_node.setAttr('colorGain', [scalar, scalar, scalar])
                                weight_node.setAttr('colorSpace', 'Raw', type='string')
                                rgb_to_hsv_node = pm.shadingNode("rgbToHsv", n="rgbToHsv", asUtility=True)
                                weight_node.outColor >> rgb_to_hsv_node.inRgb
                                rgb_to_hsv_node.outHsvV >> blend_color_node.blender
                                # Makeup base
                                base_node = pm.shadingNode("file", n=makeup_base, asTexture=True)
                                base_node.setAttr('fileTextureName', props[makeup_base]["Texture"])
                                color_as_vector = self.convert_color(props[makeup_base]["Value"])
                                base_node.setAttr('colorGain', color_as_vector)
                                base_node.outColor >> blend_color_node.color1
                                # Skin color
                                skin_node = pm.shadingNode("file", n=skin_color, asTexture=True)
                                skin_node.setAttr('fileTextureName', props[skin_color]["Texture"])
                                color_as_vector = self.convert_color(props[skin_color]["Value"])
                                skin_node.setAttr('colorGain', color_as_vector)
                                skin_node.outColor >> blend_color_node.color2

                        if "color" in avail_tex.keys() and blend_color_node is None:
                            prop = avail_tex["color"]
                            if props[prop]["Texture"] != "":
                                clr_node = pm.shadingNode("file", n=prop, asTexture=True)
                                clr_node.setAttr('fileTextureName', props[prop]["Texture"])
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                clr_node.setAttr('colorGain', color_as_vector)
                                clr_node.outColor >> surface.baseColor
                            else:
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                surface.setAttr('baseColor', color_as_vector)

                        if "opacity" in avail_tex.keys():
                            prop = avail_tex["opacity"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                scalar = float(props[prop]["Value"])
                                file_node.setAttr('colorGain', [scalar, scalar, scalar])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outColor >> surface.opacity
                                cmds.setAttr('hardwareRenderingGlobals.transparencyAlgorithm', 5)

                        if "transparency" in avail_tex.keys():
                            prop = avail_tex["transparency"]
                            surface.setAttr('transmission', props[prop]["Value"])
                            color_as_vector = self.convert_color(props[avail_tex["color"]]["Value"])
                            surface.setAttr('transmissionColor', color_as_vector)

                        if "ior" in avail_tex.keys():
                            prop = avail_tex["ior"]
                            surface.setAttr('specularIOR', props[prop]["Value"])                            

                        if "metalness" in avail_tex.keys():
                            prop = avail_tex["metalness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outAlpha >> surface.metalness

                        if "roughness" in avail_tex.keys():
                            prop = avail_tex["roughness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outAlpha >> surface.specularRoughness
                            else:
                                surface.setAttr('specularRoughness', props[prop]["Value"])

                        if "specular" in avail_tex.keys():
                            prop = avail_tex["specular"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"]) 
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outColor >> surface.specularColor

                        if "normal" in avail_tex.keys():
                            prop = avail_tex["normal"]
                            if props[prop]["Texture"] != "":
                                # Create a bump2d node for normal mapping
                                bump_node = pm.shadingNode("bump2d", asUtility=True)
                                bump_node.bumpInterp.set(1)  # 1 = Tangent Space Normals
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.outAlpha >> bump_node.bumpValue  # Use outAlpha for normal maps
                                normal_strength = props[prop]["Value"]
                                # Adjust bump depth
                                if isinstance(normal_strength, str):
                                    try:
                                        normal_strength = self.convert_color(normal_strength)[0]
                                    except Exception as e:
                                        print("Error: convert_to_standard_surface(): Error processing normal map: " + str(e) + ", setting normal_strength to 1.0")
                                        normal_strength = 1.0
                                bump_node.bumpDepth.set(float(normal_strength))
                                bump_node.outNormal >> surface.normalCamera             

                        if "bump" in avail_tex.keys():
                            prop = avail_tex["bump"]
                            if props[prop]["Texture"] != "":
                                bump_node = pm.shadingNode("bump2d", asUtility=True)
                                bump_node.bumpInterp.set(0)  # 0 = Bump
                                file_node = pm.shadingNode("file", n=shader.name() + "_" + prop + "_tx", asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                file_node.setAttr('alphaIsLuminance', True)
                                file_node.outAlpha >> bump_node.bumpValue
                                bump_node.bumpDepth.set(props[prop]["Value"])
                                bump_node.outNormal >> surface.normalCamera           

                        if "sss-radius" in avail_tex.keys():
                            if "color" in avail_tex.keys():
                                if props[avail_tex["color"]]["Texture"] != "":
                                    if clr_node:
                                        clr_node.outColor >> surface.subsurfaceColor
                                    elif blend_color_node:
                                        blend_color_node.output >> surface.subsurfaceColor
                                else:
                                    color_as_vector = self.convert_color(props[avail_tex["color"]]["Value"])
                                    surface.setAttr("subsurfaceColor", color_as_vector)

                            radius_as_vector = self.convert_color(props[avail_tex["sss-radius"]]["Value"])
                            surface.base.set(0)
                            surface.setAttr("subsurface", 1)
                            surface.setAttr("subsurfaceRadius", radius_as_vector)
                            surface.setAttr("subsurfaceScale", 0.5)

                        if not self.keep_phong:
                            pm.delete(shader)

    ## DB 2024-09-18: Stingray PBS shader implementation
    def convert_to_stingray_pbs(self):
        allshaders = self.get_materials_in_scene()
        self.load_materials()
        
        for shader in allshaders:
            # Get shading engine
            se = shader.shadingGroups()[0]
            # Get assigned shapes
            members = se.members()
            
            if members:
                split = members[0].split("Shape")
                if len(split) > 1:
                    obj_name = split[0]
                    props = self.find_mat_properties(obj_name, shader.name())

                    if props:
                        # Create Stingray PBS shader and connect to shading group
                        surface = pm.shadingNode("StingrayPBS", n=shader.name() + "_stingray", asShader=True)
                                               
                        # Connect the shader to the shading group
                        surface.outColor >> se.surfaceShader

                        avail_tex = {}
                        for tex_type, tex_info in texture_library.items():
                            for tex_name in tex_info["Name"]:
                                if tex_name in props:
                                    if tex_type in avail_tex and props[tex_name]["Texture"] == "":
                                        continue
                                    avail_tex[tex_type] = tex_name

                        # Get the name of the shader node
                        shaderfx_node = surface.name()
                        
                        # Refresh the shader to initialize all attributes
                        pm.refresh()

                        # Define the path to the Standard_Transparent.sfx preset
                        standard_path = 'Scenes/StingrayPBS/Standard.sfx'
                        transparent_path = 'Scenes/StingrayPBS/Standard_Transparent.sfx'
                        
                        if 'opacity' in avail_tex:
                            # Load the preset
                            cmds.shaderfx(sfxnode=shaderfx_node, loadGraph=transparent_path)
                        else:
                            cmds.shaderfx(sfxnode=shaderfx_node, loadGraph=standard_path)
                        
                        # Assign textures and set attributes as before

                        if "color" in avail_tex:
                            prop = avail_tex["color"]
                            if props[prop]["Texture"]:
                                # Create file node
                                clr_node = pm.shadingNode("file", n=prop + "_file", asTexture=True)
                                clr_node.setAttr('fileTextureName', props[prop]["Texture"])
                                clr_node.setAttr('colorSpace', 'sRGB', type='string')
                                # Connect outColor to base_color
                                clr_node.outColor >> surface.TEX_color_map
                                # Enable the color map
                                surface.use_color_map.set(True)
                            else:
                                color_as_vector = self.convert_color(props[prop]["Value"])
                                surface.base_color.set(color_as_vector)
                                surface.use_color_map.set(False)

                        if "opacity" in avail_tex:
                            prop = avail_tex["opacity"]
                            if props[prop]["Texture"]:
                                opacity_node = pm.shadingNode("file", n=prop + "_file", asTexture=True)
                                opacity_node.setAttr('fileTextureName', props[prop]["Texture"])
                                opacity_node.setAttr('colorSpace', 'Raw', type='string')
                                opacity_node.setAttr('alphaIsLuminance', True)
                                # Connect outAlpha to opacity
                                opacity_node.outAlpha >> surface.opacity
                                surface.use_opacity_map.set(True)
                            else:
                                surface.opacity.set(props[prop]["Value"])
                                surface.use_opacity_map.set(False)

                        if "metalness" in avail_tex.keys():
                            prop = avail_tex["metalness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                surface.setAttr('use_metallic_map', True)
                                file_node.outColor >> surface.TEX_metallic_map
                            else:
                                surface.setAttr('metallic', props[prop]["Value"])
                        
                        if "roughness" in avail_tex.keys():
                            prop = avail_tex["roughness"]
                            if props[prop]["Texture"] != "":
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                surface.setAttr('use_roughness_map', True)
                                file_node.outColor >> surface.TEX_roughness_map
                            else:
                                surface.setAttr('roughness', props[prop]["Value"])

                        if "normal" in avail_tex.keys():
                            prop = avail_tex["normal"]
                            if props[prop]["Texture"] != "":
                                # Create a normal map node
                                file_node = pm.shadingNode("file", n=prop, asTexture=True)
                                file_node.setAttr('fileTextureName', props[prop]["Texture"])
                                file_node.setAttr('colorSpace', 'Raw', type='string')
                                surface.setAttr('use_normal_map', True)
                                file_node.outColor >> surface.TEX_normal_map

                        if "ao" in avail_tex.keys():
                            prop = avail_tex["ao"]
                            if props[prop]["Texture"] != "":
                                ao_node = pm.shadingNode("file", n=prop, asTexture=True)
                                ao_node.setAttr('fileTextureName', props[prop]["Texture"])
                                ao_node.setAttr('colorSpace', 'Raw', type='string')
                                surface.setAttr('use_ao_map', True)
                                ao_node.outColor >> surface.TEX_ao_map

                        # Handle other properties as needed

                        if not self.keep_phong:
                            pm.delete(shader)
