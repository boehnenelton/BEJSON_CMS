A while back we were trying to patch a freeze when importing files and images into the CMS We tried lots of stuff and it wasn't working and I got tired of working on it so I told you that you fixed it but I lied It was never fixed and has persisted ever since to this day

I now know the cause of freeze and how to easily solve it 

Right now we currently use a JavaScript based file system API method to find and select images and file to import to the CMS 

When you file system API selector pops up it sends the app process to the background where it's killed by the OS 

I believe the solution is to utilize a flask based file to pick her system instead using Python where we browse the file system inside the app through a native custom built file browsing module 

This will ensure that they have never used something background therefore never gets killed by the Android system