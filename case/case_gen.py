import numpy as np, trimesh
from trimesh.creation import box as _box, cylinder as _cyl
from trimesh.boolean import difference as diff, union as uni
ENG='manifold'
from shapely.geometry import box as _sbox
def rrect_prism(w,h,d,r):
    return trimesh.creation.extrude_polygon(_sbox(r,r,w-r,h-r).buffer(r,join_style=1), height=d)
def bx(sx,sy,sz,x,y,z):
    b=_box(extents=[sx,sy,sz]); b.apply_translation([x+sx/2,y+sy/2,z+sz/2]); return b
def cyl(r,z0,z1,x,y,n=48):
    c=_cyl(radius=r,height=(z1-z0),sections=n); c.apply_translation([x,y,(z0+z1)/2]); return c
def frame(cx,cy,z0,h,iw,ih,pw):
    return diff([bx(iw+2*pw,ih+2*pw,h,cx-(iw/2+pw),cy-(ih/2+pw),z0),
                 bx(iw,ih,h+2,cx-iw/2,cy-ih/2,z0-1)],engine=ENG)

def text_mesh(txt, cap_h, thick):
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon
    from functools import reduce
    tp=TextPath((0,0), txt, size=20, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys=[p for p in tp.to_polygons() if len(p)>=3]
    shp=[Polygon(p).buffer(0) for p in polys]
    shp=[g for g in shp if g.area>0.05]
    from shapely.geometry import MultiPolygon
    geom=reduce(lambda a,b:a.symmetric_difference(b), shp)   # even-odd -> letter holes
    gs=list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    m=trimesh.util.concatenate([trimesh.creation.extrude_polygon(g, height=thick) for g in gs])
    ext=m.bounds[1]-m.bounds[0]
    sc=cap_h/ext[1]
    m.apply_scale([sc,sc,1.0])
    m.apply_transform(trimesh.transformations.reflection_matrix([0,0,0],[1,0,0]))  # mirror X (viewed from outside)
    return m

# ===== board (measured) =====
BL,BW,BT=101.5,54.9,1.6; comp_h=5.0
GW,GH=85.0,55.0; GDX=8.5                      # glass 85x55, 8.5mm from left (board ROTATED 180)
USB_FROMBOT=13.0; USB_LEN=8.0; USB_TALL=4.0   # micro-USB: LEFT edge, 13mm from bottom (rotated)
# ===== PN532 reader (all-in-one board, antenna built in) =====
PN_W,PN_H,PN_T=43.0,41.0,1.6
# ===== case =====
tap_h=46.0; wall=2.5; front_t=2.2; clr=0.8; top_bez=11.0; back_gap=16.0  # deep back = battery bay
lid_th=2.4; ltol=0.4; ledge_th=1.6; pw=1.6; pkt_tol=0.8
# ===== derived =====
cav_d=BT+comp_h+back_gap; out_d=front_t+cav_d
b_left=wall+clr; b_bot=wall+tap_h+clr; b_top=b_bot+BW
cav_w=BL+2*clr; out_w=cav_w+2*wall
cav_h=tap_h+clr+BW+top_bez+clr; out_h=cav_h+2*wall
op_x=b_left+GDX-0.4; op_y=b_bot-0.4; op_w=GW+0.8; op_h=min(GH,BW)+0.8
tcx=out_w/2; tcy=wall+tap_h/2; lid_z=out_d-lid_th
usb_cy=b_bot+USB_FROMBOT+USB_LEN/2
corners=[(b_left+7,b_bot+7),(b_left+BL-7,b_bot+7),(b_left+7,b_top-7),(b_left+BL-7,b_top-7)]
print(f"OUTER {out_w:.1f} x {out_h:.1f} x {out_d:.1f} mm")

# ===== BODY =====
outer=rrect_prism(out_w,out_h,out_d,4.0)  # rounded vertical corners
cav=bx(cav_w,cav_h,cav_d+1,wall,wall,front_t)
screen=bx(op_w,op_h,front_t+2,op_x,op_y,-1)
usb=bx(wall+clr+4,USB_LEN+5,USB_TALL+4,-1,usb_cy-(USB_LEN+5)/2,front_t+BT-2)  # USB opening sized for a chunky boot (~13x8)
ring=diff([cyl(18.0,-1,0.7,tcx,tcy),cyl(16.5,-1,1.0,tcx,tcy)],engine=ENG)  # thin ring GROOVE (not a big recess)
shell=diff([outer,cav,screen,usb,ring],engine=ENG)
# lid screw bosses + top/bottom rest shelves (sides open so board slides in)
bcx=[wall+8,out_w-wall-8]; bcy=wall+9; top_bcy=b_top+6.5
bcys=[bcy,top_bcy]
bosses=uni([cyl(4.0,front_t,lid_z,x,y) for x in bcx for y in bcys],engine=ENG)
shelf_d=4.0
ledge=uni([bx(cav_w,shelf_d,ledge_th,wall,wall,lid_z-ledge_th),
           bx(cav_w,shelf_d,ledge_th,wall,out_h-wall-shelf_d,lid_z-ledge_th)],engine=ENG)
# PN532 pocket on the front wall (antenna faces the card) + 2 snap clips
pn_ph=PN_T+2.5
pocket=frame(tcx,tcy,front_t,pn_ph,PN_W+pkt_tol,PN_H+pkt_tol,pw)
cxh=(PN_W+pkt_tol)/2
clips=[bx(1.4,10,1.1,tcx+cxh-1.4,tcy-5,front_t+PN_T),
       bx(1.4,10,1.1,tcx-cxh,   tcy-5,front_t+PN_T)]
def keeper(x,y):
    return diff([bx(6.4,3.0,5.4,x-3.2,y-1.5,front_t),bx(4.4,4.0,3.0,x-2.2,y-2.0,front_t+1.2)],engine=ENG)
keepers=[keeper(wall+5,b_bot-4)]
# circular speaker pocket (Ø20 mm speaker) + round sound grille
SPK_DIA,SPK_T=20.0,5.0
spk_cx=wall+clr+13.2; spk_cy=tcy+3.5              # nudge up to clear the bottom boss
R_in=SPK_DIA/2+pkt_tol/2; R_out=R_in+pw
spk_pocket=diff([cyl(R_out,front_t,front_t+SPK_T+1.5,spk_cx,spk_cy),
                 cyl(R_in,front_t-1,front_t+SPK_T+2,spk_cx,spk_cy)],engine=ENG)
spk_gap=bx(10.0, R_out-R_in+4, front_t+SPK_T+3, spk_cx-5.0, spk_cy+R_in-2, front_t-1)  # 1cm wire gap (top of ring)
spk_pocket=diff([spk_pocket,spk_gap],engine=ENG)
grille=[cyl(0.8,-1,front_t+1,spk_cx,spk_cy)]+[cyl(0.8,-1,front_t+1,spk_cx+6*np.cos(a),spk_cy+6*np.sin(a)) for a in np.linspace(0,2*np.pi,8,endpoint=False)]
MOD_L,MOD_H,MOD_T=30.0,20.0,4.0                      # charge board (measured); cradle now on the LID
mod_cx=out_w/2; mod_cy=wall+MOD_L/2+2.0; mod_wh=MOD_T+1.0   # board UPRIGHT: USB-C short edge at the bottom hole
z_bay=front_t+BT+comp_h+3            # depth where the switch sits
sw_cy=(b_bot+b_top)/2; sw_z=z_bay   # switch centered on the right edge, between the two right press-pads
sw_posts=uni([bx(2.6,5.0,5.0, out_w-wall-2.6, py-2.5, sw_z-0.25) for py in [sw_cy-7.5,sw_cy+7.5]],engine=ENG)
body=uni([shell,bosses,ledge,pocket,spk_pocket,sw_posts]+clips+keepers,engine=ENG)
# wire exit notch out the top of the pocket
notch=bx(8,pw+2,pn_ph+2,tcx-4,tcy+(PN_H+pkt_tol)/2+pw/2-0.8,front_t-1)
usbc=bx(11.0, wall+4, MOD_T+2, mod_cx-5.5, -1.5, lid_z-MOD_T-1)      # USB-C charge slot in the BOTTOM wall (under the lid cradle)
psw =bx(wall+3, 10.0, 4.5, out_w-wall-1.5, sw_cy-5, sw_z)            # switch actuator slot (right wall)
sw_pilots=[bx(3.8,1.9,1.9, out_w-wall-3.8, py-0.95, sw_z+1.3) for py in [sw_cy-7.5,sw_cy+7.5]]   # screw pilots into the posts
ledge_notch=bx(MOD_H+2*pw+4, 8, ledge_th+2, mod_cx-(MOD_H+2*pw+4)/2, wall-1, lid_z-ledge_th-1)  # clear bottom shelf for the lid cradle
body=diff([body,notch,usbc,psw,ledge_notch]+sw_pilots+grille+[cyl(1.4,front_t+2,lid_z+0.1,x,y) for x in bcx for y in bcys],engine=ENG)
# --- ENGRAVED "TAP" (debossed into the flat front; prints clean face-down) ---
tap=text_mesh("TAP", 10.0, 1.0)
tb=tap.bounds; ctr=(tb[0]+tb[1])/2
tap.apply_translation([tcx-ctr[0], tcy-ctr[1], -0.2])    # z -0.2..0.8 -> 0.8mm deep engrave
body=diff([body,tap],engine=ENG)
body.export('case_body.stl')

# ===== LID (recessed, board press-pads) =====
lid=bx(cav_w-2*ltol,cav_h-2*ltol,lid_th,wall+ltol,wall+ltol,lid_z)
pad_short=1.2      # base shortening for all lid press-pads
pad_short_L=1.9    # extra shortening for the far side (edge OPPOSITE the USB = "left" from the back)
pads=uni([cyl(3.5, front_t+BT+(pad_short_L if cx>out_w/2 else pad_short), lid_z, cx,cy) for cx,cy in corners],engine=ENG)
holesL=[cyl(1.9,lid_z-0.1,out_d+0.1,x,y) for x in bcx for y in bcys]
vents=[bx(30,3,lid_th+2,out_w/2-15,out_h*0.35+i*7,lid_z-1) for i in range(3)]
BAT_W,BAT_H,bat_wh=55.0,40.0,5.0                 # battery corral (measure your cell; adjust)
bat_cx=out_w/2; bat_cy=(b_bot+b_top)/2
bat_frame=frame(bat_cx,bat_cy,lid_z-bat_wh,bat_wh,BAT_W+1.5,BAT_H+1.5,pw)
bat_gap=bx(12,pw+2,bat_wh+2, bat_cx-6, bat_cy-(BAT_H+1.5)/2-pw, lid_z-bat_wh-1)  # wire exit (bottom)
bat_frame=diff([bat_frame,bat_gap],engine=ENG)
modl_frame=frame(mod_cx,mod_cy,lid_z-mod_wh,mod_wh,MOD_H+pkt_tol,MOD_L+pkt_tol,pw)   # charge-board cradle (UPRIGHT: 20 wide x 30 tall)
modl_gap=bx(12,pw+2,mod_wh+2, mod_cx-6, mod_cy-(MOD_L+pkt_tol)/2-pw, lid_z-mod_wh-1)  # USB/wire gap (bottom short edge)
modl_frame=diff([modl_frame,modl_gap],engine=ENG)
led_peek=bx(5.0, 8.0, lid_th+2, mod_cx+5.3, mod_cy+4.5, lid_z-1)   # peek slot over the charge LEDs (top-right: 1mm from right edge, 4-9mm from top)
lid=diff([uni([lid,pads,bat_frame,modl_frame],engine=ENG)]+holesL+vents+[led_peek],engine=ENG)
lid.export('case_lid.stl')

# ===== STAND =====
sside=6.0; stand_w=out_w+2*sside; base_depth=out_d+34; base_th=4.0
foot_y=out_d+14; sup_len=70.0; sup_th=6.0; recline=18
base=bx(stand_w,base_depth,base_th,0,0,0)
lip=bx(stand_w,3.0,13.0,0,3.0,base_th-0.1)
sup=_box(extents=[stand_w,sup_th,sup_len]); sup.apply_translation([stand_w/2,0,sup_len/2])
sup.apply_transform(trimesh.transformations.rotation_matrix(np.radians(recline),[1,0,0],[0,0,0]))
sup.apply_translation([0,foot_y,base_th-0.1])
uni([base,lip,sup],engine=ENG).export('case_stand.stl')
for n in ['case_body','case_lid','case_stand']:
    m=trimesh.load(f'{n}.stl'); print(f"{n}: watertight={m.is_watertight} bbox={np.round(m.extents,1)}")
