! -*- f90 -*-
! - Adapted by DG for f2py 2018/10/14
      module ImageClass
!
!
!
      interface put_image
       module procedure put_image_in
       module procedure put_image_rl
      end interface put_image

      interface get_image
       module procedure get_image_in
       module procedure get_image_rl
      end interface get_image

      interface check_image
       module procedure check_image_in
       module procedure check_image_rl
      end interface check_image

      interface put_header
       module procedure put_header_in
       module procedure put_header_rl
       module procedure put_header_st
       module procedure put_header_lg
      end interface put_header

      interface get_header
       module procedure get_header_in
       module procedure get_header_rl
       module procedure get_header_st
       module procedure get_header_lg
      end interface get_header

    contains


      subroutine printerror(status)

        integer, intent (inout) :: status
        character errtext*30,errmessage*80
          
        if (status .le. 0)return

        call ftgerr(status,errtext)
        print *,'FITSIO Error Status =',status,': ',errtext
        

        call ftgmsg(errmessage)
        do while (errmessage .ne. ' ')
           print *,errmessage
           call ftgmsg(errmessage)
        end do
        stop 
      end subroutine printerror
        
      subroutine tranhd( inunit, outunit,KEYWORD )
      character( len = * ), intent( in     ) :: KEYWORD
      integer         , intent( in     ) :: inunit, outunit


      character( len = 80 ) :: COMMENT
      character( len = 68 ) :: stvar
      integer :: stat 

      stat = 0
      
      call ftgkys( inunit,KEYWORD,stvar,COMMENT,stat)

      if ( stat > 0 )  then
         call printerror(stat)
      end if 

      if (stat == 202 ) then
        stat = 0
        print *, KEYWORD, ' is empty'
        call ftpkys( outunit,KEYWORD,'0.0','Empty header',stat)
      else
       call ftpkys( inunit,KEYWORD,stvar,COMMENT,stat)
      end if
      end subroutine tranhd

      subroutine put_header_in( filename, KEYWORD, var, COMMENT )
      character( len = * ), intent( in     ) :: filename, KEYWORD
      integer         , intent( in     ) :: var
      character( len = * ), intent( in     ), optional :: COMMENT

      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: stat 

      stat = 0

      
      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?



      call ftopen( fits,trim(filename),rwmode, blocksize,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if 
      
      if ( present ( COMMENT) ) then
         call ftpkyj( fits,KEYWORD,var,COMMENT,stat)
      else
         call ftpkyj( fits,KEYWORD,var,'',stat)
      end if

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if

      end subroutine put_header_in
!
      subroutine put_header_lg( filename, KEYWORD, var, COMMENT )
      character( len = * ), intent( in     ) :: filename, KEYWORD
      logical         , intent( in     ) :: var
      character( len = * ), intent( in     ), optional :: COMMENT
      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: stat

      
      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      stat = 0


      call ftopen( fits,trim(filename),rwmode, blocksize,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if

      
      if ( present ( COMMENT) ) then
        call ftpkyl( fits,KEYWORD,var,COMMENT,stat)
      else
        call ftpkyl( fits,KEYWORD,var,'',stat)
     end if

     if ( stat > 0 )  then
         call printerror( stat )
      end if

     
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      

      end subroutine put_header_lg
!
!
!
      subroutine put_header_rl( filename, KEYWORD, var, COMMENT )
      character( len = * ), intent( in     ) :: filename, KEYWORD
      real         , intent( in     ) :: var
      character( len = * ), intent( in     ), optional :: COMMENT
      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: decimals
      integer :: stat      
       

      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      decimals = -8
      stat = 0

      call ftopen( fits,trim(filename),rwmode, blocksize,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if

      
      if ( present ( COMMENT) ) then
        call ftpkye( fits,KEYWORD,var,decimals,COMMENT,stat)
      else
        call ftpkye( fits,KEYWORD,var,decimals,'',stat)
     end if

      if ( stat > 0 )  then
         call printerror( stat )
      end if
     
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      

      end subroutine put_header_rl
!
      subroutine put_header_st( filename, KEYWORD, var, COMMENT )
      character( len = * ), intent( in     ) :: filename, KEYWORD, var
      character( len = * ), intent( in     ), optional :: COMMENT

      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: stat


      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      stat = 0

      call ftopen( fits,trim(filename),rwmode,blocksize,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      if ( present ( COMMENT) ) then
        call ftpkys( fits,KEYWORD,trim(var),COMMENT,stat)
      else
        call ftpkys( fits,KEYWORD,trim(var),'',stat)
     end if

     if ( stat > 0 )  then
         call printerror( stat )
      end if
     
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      

      end subroutine put_header_st
!
!
!
      subroutine get_header_rl( filename, KEYWORD, var, comment )
      character( len = * ), intent( in     ) :: filename, KEYWORD
      real          , intent( in  out  ) :: var
      character(len=72) , intent( in  out  ) :: comment


      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: stat

     
      comment = '' 
      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      stat = 0

      
      call ftopen( fits,trim(filename),rwmode, blocksize,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftgkye( fits,trim(KEYWORD),var,comment,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      
      end subroutine get_header_rl

      subroutine get_header_real( filename, KEYWORD, var )
      character( len = * ) :: filename, KEYWORD
      real          :: var
      character(len=72) :: comment

      
      !f2py intent(in) filename, KEYWORD
      !f2py intent(out) var

      call get_header_rl( filename, KEYWORD, var, comment )

      end subroutine get_header_real
!
!
      subroutine get_header_lg( filename, KEYWORD, var, comment )
      character( len = * ), intent( in     ) :: filename, KEYWORD
      logical           , intent( in  out  ) :: var
      character(len=72) , intent( in  out  ) :: comment

      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: stat
     
      comment = '' 
      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      stat = 0

      call ftopen( fits,trim(filename),rwmode, blocksize,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if

      
      call ftgkyl( fits,trim(KEYWORD),var,comment,stat)


      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      
      end subroutine get_header_lg
!
!
!
      subroutine get_header_in( filename, KEYWORD, var, comment )
      character( len = * ), intent( in     ) :: filename, KEYWORD
      integer             , intent( in out ) :: var
      character(len=72)   , intent( in out ) :: comment

      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: stat

     
      comment = '' 
      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      stat = 0
      
      call ftopen( fits,trim(filename),rwmode, blocksize,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if

      
      call ftgkyj( fits,trim(KEYWORD),var,comment,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if

      
      end subroutine get_header_in
!
!
!
!
      subroutine get_header_st( filename, KEYWORD, var, comment )
      character( len = * ), intent( in     ) :: filename, KEYWORD
      character( len = 68 ), intent( in out ) :: var
      character( len = 72 ), intent( in out ) :: comment


      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: stat      
      
      comment = ''
      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      stat = 0

      call ftopen( fits,trim(filename),rwmode, blocksize,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftgkys( fits,trim(KEYWORD),var,comment,stat)

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      
      end subroutine get_header_st

      subroutine get_header_string( filename, KEYWORD, var )
      character( len = * ) :: filename, KEYWORD
      character( len = 68 ) :: var
      character( len = 72 ) :: comment

      !f2py intent(in) filename, KEYWORD
      !f2py intent(out) var

      call get_header_st( filename, KEYWORD, var, comment )

      end subroutine get_header_string

!
!
!
      subroutine put_image_in( filename, image, nc, nr )
      character( len = * ), intent( in     ) :: filename
      integer          , intent( in     ) :: nc, nr
      integer          , intent( in     ) :: image( nc, nr )

      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: naxis
      integer :: bitpix
      integer :: naxes( 2 )
      integer :: stat
      logical :: simple
      logical :: extend
      
      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      stat = 0
      
      simple = .true.
      bitpix = 16
      naxis  = 2
      naxes  = (/ nc, nr /)
      extend = .false.
      
      call ftinit( fits, trim(filename), blocksize, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftphpr( fits, simple, bitpix, naxis, naxes, 0, 1, extend, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftp2dj( fits, group, nc, nc, nr, image, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      

      end subroutine put_image_in
!
!
!
      subroutine put_image_rl( filename, image, nc, nr )
      character( len = * ), intent( in     ) :: filename
      integer       , intent( in     ) :: nc, nr
      real          , intent( in     ) :: image( nc, nr )

      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: blocksize
      integer :: naxis
      integer :: bitpix
      integer :: stat
      integer :: naxes( 2 )
      logical :: simple
      logical :: extend
      
      fits    = 101             !- unit
      rwmode  = 1               !- rwmode, readwrite
      group   = 0               !- group, 0 for non-grouped
      blocksize = 1             !- eh?
      stat = 0
      
      simple = .true.
      bitpix = -32
      naxis  = 2
      naxes  = (/ nc, nr /)
      extend = .false.
      
      call ftinit( fits, trim(filename), blocksize, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      
      call ftphpr( fits, simple, bitpix, naxis, naxes, 0, 1, extend, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftp2de( fits, group, nc, nc, nr, image, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      
      end subroutine put_image_rl
!
!
!
      subroutine get_image_in( filename, image, nc, nr )
      character( len = * ), intent( in     ) :: filename
      integer          , intent( in     ) :: nc, nr
      integer          , intent( in out ) :: image( nc, nr )
      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: fpixel
      logical :: anyf
      integer :: stat

      integer :: nullval
      character( len = 72 ) comment, stpstring
      

      fits    = 101             !- unit
      rwmode  = 0               !- rwmode, read-only
      group   = 0               !- group, 0 for non-grouped
      fpixel  = 0               !- first pixel
      nullval = 0               !- null value to substitute
      stat = 0
      
      call ftiopn( fits, trim(filename), rwmode, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
          
      call ftg2dj( fits, group, nullval, nc, nc, nr, image, anyf, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if

      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      end subroutine get_image_in
!
!
!
      subroutine check_image_in( filename, image, nc, nr )
      character( len = * ), intent( in     ) :: filename
      integer          , intent( in     ) :: nc, nr
      integer          , intent( in out ) :: image( nc, nr )

      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: fpixel
      integer :: stat
      logical :: anyf

      integer :: nullval
      character( len = 72 ) comment
      

      fits    = 101             !- unit
      rwmode  = 0               !- rwmode, read-only
      group   = 0               !- group, 0 for non-grouped
      fpixel  = 0               !- first pixel
      nullval = 0               !- null value to substitute
      stat = 0
      
      call ftiopn( fits, trim(filename), rwmode, stat )
      if ( stat > 0 )  then
         call printerror( stat )
      end if

      
      call ftg2dj( fits, group, nullval, nc, nc, nr, image, anyf, stat )
      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )
      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      
      if( anyf ) then 
        print *, filename, ' 0'
      else
        print *, filename, ' 1'
      end if

      end subroutine check_image_in
!
!
!
      subroutine get_image_rl( filename, image, nc, nr)
      character( len = * ), intent( in     ) :: filename
      integer       , intent( in     ) :: nc, nr
      real          , intent( in out ) :: image( nc, nr )

      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: fpixel
      integer :: stat
      logical :: anyf
      real :: nullval
      character( len = 72 ) comment, stpstring
      
      fits    = 101             !- unit
      rwmode  = 0               !- rwmode, read-only
      group   = 0               !- group, 0 for non-grouped
      fpixel  = 0               !- first pixel
      nullval = 0.0             !- null value to substitute
      stat = 0

      call ftiopn( fits, trim(filename), rwmode, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if

      
      call ftg2de( fits, group, nullval, nc, nc, nr, image, anyf, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      end subroutine get_image_rl
!
!
!
!
      subroutine check_image_rl( filename, image, nc, nr )
      character( len = * ), intent( in     ) :: filename
      integer       , intent( in     ) :: nc, nr
      real          , intent( in out ) :: image( nc, nr )
      
      integer :: fits
      integer :: rwmode
      integer :: group
      integer :: fpixel
      logical :: anyf
      integer :: stat
      real :: nullval
      character( len = 72 ) comment
      
      fits    = 101             !- unit
      rwmode  = 0               !- rwmode, read-only
      group   = 0               !- group, 0 for non-grouped
      fpixel  = 0               !- first pixel
      nullval = 0.0             !- null value to substitute
      stat = 0

      call ftiopn( fits, trim(filename), rwmode, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftg2de( fits, group, nullval, nc, nc, nr, image, anyf, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
      call ftclos( fits, stat )

      if ( stat > 0 )  then
         call printerror( stat )
      end if
      
     
      if( anyf ) then
        print *, filename,  ' 0' 
      else
        print *, filename,  ' 1' 
      end if

      end subroutine check_image_rl
!
      subroutine deletefile(filename)
      character( len = * ), intent( in     ) :: filename

      logical :: exists
      integer :: ounit
      
      inquire(file=filename,exist=exists)

      if( exists ) then
         ounit = 86
         open(ounit,file=filename,status='old')
         close(ounit,status='delete')
      endif

      return

      end subroutine deletefile

      subroutine getfile(filename,test,ptffile)
      character( len = * ), intent( in out ) :: filename
      character( len = * ), intent( in ) :: ptffile
      logical, intent( in out ) :: test

      logical :: exists, running
      integer :: ounit

      running = .true.      

      do while (running)

       inquire(file=ptffile,exist=exists)

       if( exists ) then

         print *, 'The file exists'

         ounit = 86
         open(ounit,file=ptffile,status='old')
         read(86,*) filename

         if (trim(filename) == 'stop') then
           test = .false.
           running = .false.
           close(ounit,status='delete')
         else
           test = .true.
           running = .false.
           close(ounit,status='delete')
         end if


       else

         print *, 'The file doesnt exist, I will sleep'

         call system('sleep 5') 
         running = .true.

       endif

      end do

      return

      end subroutine getfile
      
      
      end module ImageClass

