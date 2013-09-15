Cloud-Orchestration-Layer
=========================

A Cloud Orchestration Layer: Creating/Deleting/Quering and Scheduling Virtual Machines(VMs) in a given Network and also attach Storage Block Devices to the VMs on demand

How does it work?

Write the information of the machines in file named: machines

And also the Location of the VM image file in file name: Images

cd bin

./script machines Images


Now, by curl calls or REST calls, you can create/delete/query a VM, and also attach Storage Block devies to it by:

Creating a VM:

-> http://localhost:3000/vm/create?name=test_vm&instance_type=type


Quering a VM:

-> http://localhost:3000/vm/query?vmid=vmid


Destroy a VM:

-> http://localhost:3000/vm/destroy?vmid=vmid


List VM types:

-> http://localhost:3000/vm/types


Create a Volume Block Storage:

-> http://localhost:3000/volume/create?name=test­volume&size=10


Query a Volume Block Storage:

-> http://localhost:3000/volume/query?volumeid=volumeid


Destroy a Volume Block Storage:

-> http://localhost:3000/volume/destroy?volumeid=volumeid


Attach a Block Storage Device:

-> http://localhost:3000/volume/attach?vmid=vmid&volumeid=volumeid


Detach a Block Storage Device:

-> http://localhost:3000/volume/detach?volumeid=volumeid
