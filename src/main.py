# -*- coding: utf-8 -*-
import time
from flask import Flask, request, session, url_for, redirect, \
     render_template, abort, g, flash, _app_ctx_stack, jsonify
import json
import libvirt
import os,sys
import rados
import rbd
import re
from random import choice
import subprocess
import xml.etree.ElementTree as ET
# configuration
app = Flask(__name__)

####################################################################################################################
########################################## Global Variales #########################################################
####################################################################################################################
VM_TYPES_FILE = "Vm_types"
IMAGE_FILE = sys.argv[2]
VM_IMG = []
FULL_VM_IMG = []
VM_ID_LIST = []
VM_NAME = []
VM = {}
PM_list = []
pm_chosen = ""
pm_chosen_dict = {}
pm_len = 0
mark = 0


POOL_NAME = 'try-pool'
CONF_FILE = '/etc/ceph/ceph.conf'
BLOCK_CONFIG_XML = 'attach.xml'
HOST_NAME = 'vishrut-Vostro-1015'

########################################## Connection ############################################################
radosConnection = rados.Rados(conffile=CONF_FILE)
radosConnection.connect()
if POOL_NAME not in radosConnection.list_pools():                                
            radosConnection.create_pool(POOL_NAME)
ioctx = radosConnection.open_ioctx(POOL_NAME)

rbdInstance = rbd.RBD()

###################################################################################################################
def getHostName():
     
    global HOST_NAME
    monProc = subprocess.Popen("ceph mon_status", shell=True, bufsize=0, stdout=subprocess.PIPE, universal_newlines=True)
    monDict = eval(monProc.stdout.read())
    HOST_NAME = monDict['monmap']['mons'][0]['name']

#######################
VOLUME_DICT = {}
vol_id_list = []
vol_name = []
#######################

####################################################################################################################
########################################## REST funcitons #########################################################
####################################################################################################################

@app.route("/volume/create",methods=['POST', 'GET'])
def volumeCreate():
     
    name = str(request.args.get('name',''))
    size = int(request.args.get('size',''))
    
    global VOLUME_DICT
    global vol_name
    if name in vol_name:
        return jsonify(volumeid=0)

    size = (1024**3) * size
    global ioctx
    global rbdInstance
    try:
        rbdInstance.create(ioctx,name,size)
        os.system('sudo rbd map %s --pool %s --name client.admin'%(name,POOL_NAME))
    except:
        return jsonify(volumeid=0)   

    global vol_id_list

    for j in range(10000):
        if j in vol_id_list:
            continue
        else:
            volumeID = str(j)
            vol_id_list.append(j)
            break
    tempBlock = {   
                    'name':name,
                    'size':size / (1024**3),
                    'status': "available",
                    'vmid':None,
                    'dev_name':getDeviceName(), 
                }
    VOLUME_DICT[volumeID] = tempBlock
    vol_name.append(name)
    return jsonify(volumeid=volumeID)

@app.route("/volume/query",methods=['POST', 'GET'])
def volumeQuery():
     
    volumeId = str(request.args.get('volumeid',''))
    global VOLUME_DICT
    #print VOLUME_DICT
    
    if volumeId not in VOLUME_DICT.keys():
        return jsonify(error = "volumeid : %s does not exist"%(volumeId))

    if VOLUME_DICT[volumeId]['status'] == 'attached':
        return jsonify(volumeid = volumeId,
                       name = VOLUME_DICT[volumeId]['name'],
                       size = VOLUME_DICT[volumeId]['size'],
                       status = VOLUME_DICT[volumeId]['status'],
                       vmid = VOLUME_DICT[volumeId]['vmid'],
                       )

    elif VOLUME_DICT[volumeId]['status'] == 'available':
        return jsonify(volumeid = volumeId,
                       name = VOLUME_DICT[volumeId]['name'],
                       size = VOLUME_DICT[volumeId]['size'],
                       status = VOLUME_DICT[volumeId]['status'],
                       )
    
    else:
        return jsonify(error = "volumeid : %s does not exist"%(volumeId))

@app.route("/volume/destroy",methods=['POST', 'GET'])
def volumeDestroy():
     
    volumeId = str(request.args.get('volumeid',''))
    global VOLUME_DICT
    if volumeId not in VOLUME_DICT.keys():
        return jsonify(status=0)
    if VOLUME_DICT[volumeId]['status'] == 'attached':
        return jsonify(status=0)


    imageName = str(VOLUME_DICT[volumeId]['name'])

    try:
        os.system('sudo rbd unmap /dev/rbd/%s/%s'%(POOL_NAME,imageName))
        rbdInstance.remove(ioctx,imageName)
    except:
        return jsonify(status=0)  

    del VOLUME_DICT[volumeId]
    return jsonify(status=1)

@app.route("/volume/attach",methods=['POST', 'GET'])
def volumeAttach():
     
    vmId = int(request.args.get('vmid',''))
    volumeId = str(request.args.get('volumeid',''))

    global VOLUME_DICT
    global VM_ID_LIST

    if volumeId not in VOLUME_DICT.keys():
        return jsonify(status=0)
    if VOLUME_DICT[volumeId]['status'] == 'attached':
        return jsonify(status=0)
    if vmId not in VM_ID_LIST:    
        return jsonify(status=0)
    
    global pm_chosen
    global VM
    global BLOCK_CONFIG_XML
    
    imageName = str(VOLUME_DICT[volumeId]['name'])
    conn = libvirt.open("qemu+ssh://"+pm_chosen_dict[str(vmId)]+"/system")
    dom = conn.lookupByName(VM[str(vmId)]['name'].strip("\r"))
    configXML = blockGetXML(BLOCK_CONFIG_XML,imageName, VOLUME_DICT[volumeId]['dev_name'])
    
    try:
        dom.attachDevice(configXML)
        conn.close()
    except:
        conn.close()
        return jsonify(status=0) 
    
    VOLUME_DICT[volumeId]['status'] = "attached"
    VOLUME_DICT[volumeId]['vmid'] = str(vmId)
    return jsonify(status=1)


@app.route("/volume/detach",methods=['POST', 'GET'])
def volumeDetach():
     
    volumeId = str(request.args.get('volumeid',''))
    global VOLUME_DICT
    global VM_ID_LIST
    if volumeId not in VOLUME_DICT.keys():
        return jsonify(status=0)
    if VOLUME_DICT[volumeId]['status'] == 'available':
        return jsonify(status=0)
    global pm_chosen_dict
    global VM
    imageName = str(VOLUME_DICT[volumeId]['name'])

    conn = libvirt.open("qemu+ssh://"+pm_chosen_dict[str(VOLUME_DICT[volumeId]['vmid'])]+"/system")
    dom = conn.lookupByName(VM[str(VOLUME_DICT[volumeId]['vmid'])]['name'].strip("\r"))

    global BLOCK_CONFIG_XML
    configXML = blockGetXML(BLOCK_CONFIG_XML,imageName, VOLUME_DICT[volumeId]['dev_name'])
    try:
        dom.detachDevice(configXML)
        conn.close()
    except:
        conn.close()
        return jsonify(status=0) 
    
    VOLUME_DICT[volumeId]['status'] = "available"
    VOLUME_DICT[volumeId]['vmid'] = None
    return jsonify(status=1)


@app.route('/vm/query', methods=['GET'])
def query():
    """ Query to get details of a VM """
    
    args = request.args
    vmid = args['vmid']
    conn = libvirt.open("qemu+ssh://"+pm_chosen_dict[str(vmid)]+"/system")
    dom = conn.lookupByName(VM[vmid]['name'].strip("\r"))
    infos = dom.info()
    if infos[1] == 512000:
        it = 1
    elif infos[1] == 1024000:
        it = 2
    elif infos[1] == 2048000:
        it = 3

    #result = '{\n"vmid":%s\n"name":%s\n"instance_type":%s\n}' % (vmid, VM[vmid]['name'], str(it))
    return jsonify(vmid = vmid,
            name = VM[vmid]['name'],
            instace_type = str(it))

@app.route('/vm/create', methods=['GET'])
def create():
    """ Create a VM """

    args = request.args
    Vm_name = str(args['name'])
    Vm_type_id = int(args['instance_type'])
    Vm_image_id = int(args['image_id'])
    vm_details = get_vm_types(Vm_type_id)

    vm_cpu = vm_details['cpu']
    vm_ram = vm_details['ram']
    vm_disk = vm_details['disk']
    for vm in VM_IMG:
        if vm['id'] == Vm_image_id:
            vm_image_name = vm['name'].split("/")[-1].strip("\r")
            imagePath = vm['name'].split(":")[0].strip("\r")
                #print list(vm_image_name)
    for vm in FULL_VM_IMG:
        if vm['id'] == Vm_image_id:
            vm_image_path = vm['name']
        
        # Schedular
    global pm_chosen
    pm_chosen = Scheduler(vm_cpu, vm_ram, vm_disk)
    user_name = pm_chosen.split("@")[0]
        #print list(user_name)
    send_image(pm_chosen, vm_image_path)
        
    global VM_ID_LIST
    global VM
    global pm_chosen_dict
    if len(VM_ID_LIST)==0:
        i = 1
    else:
        i = int(VM_ID_LIST[-1])+1
    vmid = i
    VM_ID_LIST.append(vmid)
    pm_chosen_dict[str(vmid)] = pm_chosen
    VM[str(vmid)] = {}
    VM[str(vmid)]['name'] = Vm_name
    VM[str(vmid)]['Physical_machine'] = pm_chosen
    xml = """<domain type='qemu' id='%s'><name>%s</name><memory>%s</memory>            <currentMemory>512000</currentMemory>            <vcpu>%s</vcpu>            <os>            <type arch='i686' machine='pc-1.0'>hvm</type>            <boot dev='hd'/>            </os>        <features>            <acpi/>            <apic/>            <pae/>        </features>        <clock offset='utc'/>  <on_poweroff>destroy</on_poweroff>  <on_reboot>restart</on_reboot>  <on_crash>restart</on_crash>  <devices>    <emulator>/usr/bin/qemu-system-i386</emulator>    <disk type='file' device='disk'>      <driver name='qemu' type='qcow2'/>      <source file='%s' />      <target dev='hda' bus='ide'/>      <alias name='ide0-0-0'/>      <address type='drive' controller='0' bus='0' unit='0'/>    </disk>    <controller type='ide' index='0'>      <alias name='ide0'/>      <address type='pci' domain='0x0000' bus='0x00' slot='0x01' function='0x1'/>    </controller>    <interface type='network'>      <mac address='52:54:00:82:f7:43'/>      <source network='default'/>      <target dev='vnet0'/>      <alias name='net0'/>      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x0'/>    </interface>    <serial type='pty'>      <source path='/dev/pts/2'/>      <target port='0'/>      <alias name='serial0'/>    </serial>    <console type='pty' tty='/dev/pts/2'>      <source path='/dev/pts/2'/>      <target type='serial' port='0'/>      <alias name='serial0'/>    </console>    <input type='mouse' bus='ps2'/>    <graphics type='vnc' port='5900' autoport='yes'/>    <sound model='ich6'>      <alias name='sound0'/>      <address type='pci' domain='0x0000' bus='0x00' slot='0x04' function='0x0'/>    </sound>    <video>      <model type='cirrus' vram='9216' heads='1'/>      <alias name='video0'/>      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x0'/>    </video>    <memballoon model='virtio'>      <alias name='balloon0'/>      <address type='pci' domain='0x0000' bus='0x00' slot='0x05' function='0x0'/>    </memballoon>  </devices>  <seclabel type='dynamic' model='apparmor' relabel='yes'>    <label>libvirt-10a963ef-9458-c30d-eca3-891efd2d5817</label>    <imagelabel>libvirt-10a963ef-9458-c30d-eca3-891efd2d5817</imagelabel> </seclabel></domain>""" % (i, Vm_name, str(int(vm_ram)*1000), str(vm_cpu), str(imagePath))


    try:
        conn = libvirt.open("qemu+ssh://"+pm_chosen_dict[str(vmid)]+"/system")
        conn.defineXML(xml)
        dom = conn.lookupByName(Vm_name)
        dom.create()
        result = "{\n%s\n}" % str(vmid)
        conn.close()
        #return result
        return jsonify(status=1)
    except:
        conn.close()
        #return str(0)
        return jsonify(status=0)

@app.route('/vm/destroy', methods=['GET'])
def destroy():
    """ Destroy a VM """

    args = request.args
    vmid = args['vmid']
    conn = libvirt.open("qemu+ssh://"+pm_chosen_dict[str(vmid)]+"/system")
    dom = conn.lookupByName(VM[vmid]['name'])
    try:
        dom.destroy()
        conn.close()
        return jsonify(status=1)
        #return str(1)
    except:
        conn.close()
        return jsonify(status=0)
        #return str(0)

@app.route('/image/list', methods=['GET'])
def image():
    """ List of all Images """
    
    return get_list_images()

@app.route('/vm/types', methods=['GET'])
def types():
    """ List of vm types """
    
    f = open("Vm_types", "r")
    l = f.read()
    return l
####################################################################################################################
########################################## Helper funcitons #########################################################
####################################################################################################################

def Scheduler(cpu, ram, disk):
    """ Schedukar for selecting pms """

    global mark
    for pms in range(len(PM_list)):
        if pms == mark:
            mark = (pms + 1)%pm_len
            os.system(" ssh " + PM_list[pms] +" free -k | grep 'Mem:' | awk '{ print $4 }' >> data")
            os.system(" ssh " + PM_list[pms] +" grep processor /proc/cpuinfo | wc -l >> data")
            f = open("data", "r")

            pm_ram = f.readline().strip("\n")
            pm_cpu = f.readline().strip("\n")
            os.system("rm -rf data")
            if int(pm_ram) >= int(ram):
                if int(pm_cpu) >= int(cpu):
                    return PM_list[pms]
            if pms == len(PM_LIST-1):
                pms = 0

def update_PM_list():

    f = open(sys.argv[1], "r")
    global PM_list
    global pm_len
    PM_list = []
    for i in f.readlines():
        i = i.strip('\n')
        PM_list.append(i.strip("\r"))

    pm_len = len(PM_list)

def get_vm_types(tid=None):

    f = open(VM_TYPES_FILE, "r")
    val = json.loads(f.read())[u'types']
    if tid!=None:
        for i in val:
            if i[u'tid'] == tid:
                return i
    else:
        return val
    return 0

def send_image(pm, image_path):
    
    image_path = image_path.strip("\r")
    if pm == image_path.split(":")[0]:
        return
    os.system("ssh " + pm + " rm /home/"+pm.split("@")[0]+"/"+image_path.split("/")[-1])
    bash_command = "scp " + image_path + " " + pm + ":/home/" + pm.split("@")[0] + "/"
    #print bash_command
    os.system(bash_command)



def make_image_list():

    #fin = open(sys.argv[2],"r")
    #for line in fin.readlines():
        #@ToDo: SCP command and also copy the public key
        #os.system("rm -rf ~/images;mkdir ~/images")
    #    line = list(line)
    #    for i in line:
    #        if i == "\n" or i=="\r":
    #            line.remove(i)
    #    line = ''.join(line)
    #    name = line.split(":")[0].split("@")[0]
    #    bash_command = "scp " + line.split(":")[1][:-1] + " " + line.split(":")[0] + ":/home/"+name+"/"
    #    os.system(bash_command)

    #images = os.listdir("/home/vishrut/images")
    #os.system("ls ~/*.img > image_list")
    f = open(sys.argv[2], "r")
    images = []
    img = []
    for i in f.readlines():
        i = i.strip("\r")
        img.append(i.strip("\n"))
        i = i.split(":")[1]
        images.append(i.strip("\n"))
    #os.system("rm -rf image_list")
    i = 1
    j = 1
    global VM_IMG
    global FULL_VM_IMG
    VM_IMG = []
    for image in img:
        t_dict = {}
        t_dict['id'] = i
        t_dict['name'] = image
        FULL_VM_IMG.append(t_dict)
        j = j + 1
    for image in images:
        temp_dict = {}
        temp_dict['id'] = i
        temp_dict['name'] = image
        VM_IMG.append(temp_dict)
        i = i + 1

def get_list_images():

    json_ret_val ='{\n"images":['
    for vm in VM_IMG:
        
        json_ret_val += "{"
        for key in vm.keys()[:-1]:
	        json_ret_val += '"%s":"%s",'%(key,vm[key])
        key = vm.keys()[-1]
        json_ret_val += '"%s":"%s"}'%(key,vm[key])
        
    json_ret_val+="]\n}\n"
    return json_ret_val


def blockGetXML(xmlFile,imageName,dev_name):
     
    tree = ET.parse(xmlFile)
    root = tree.getroot()
    imageName = POOL_NAME + '/' + imageName
    global HOST_NAME                          
    root.find('source').attrib['name'] = imageName
    root.find('source').find('host').attrib['name'] = HOST_NAME
    root.find('target').attrib['dev'] = dev_name
                                                      
    #print ET.tostring(root)
    return ET.tostring(root)

def getDeviceName():
    
    alpha = choice('efghijklmnopqrstuvwxyz')
    numeric = choice([x for x in range(1,10)])

    return 'sd' + str(alpha) + str(numeric)

if __name__ == '__main__':
    make_image_list()
    update_PM_list()
    getHostName()
    app.run()

