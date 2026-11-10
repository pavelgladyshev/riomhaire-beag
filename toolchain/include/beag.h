/* beag.h - the display and keyboard of the BEAG computer */
#ifndef BEAG_H
#define BEAG_H

/* Memory-mapped input/output registers (see the memory map in lecture 5.2). Their addresses come
   from the memory map (beag_memory.txt): beagcc defines __BEAG_DISPLAY__ and __BEAG_KEYBOARD__,
   and __BEAG_DEVICE_NAME__ for each 'device NAME ADDRESS' line. */
#ifdef __BEAG_DISPLAY__
#define BEAG_DISPLAY   (*(volatile int *)__BEAG_DISPLAY__)        /* write a character code to print it   */
#endif
#ifdef __BEAG_KEYBOARD__
#define BEAG_KBD_READY (*(volatile int *)__BEAG_KEYBOARD__)       /* 1 when a key is waiting, otherwise 0  */
#define BEAG_KBD_DATA  (*(volatile int *)(__BEAG_KEYBOARD__ + 1)) /* the waiting key; reading removes it   */
#endif

int kbhit(void);                      /* 1 if a key is waiting (getchar will not wait)       */
int read_line(char *buf, int size);   /* read a line, showing it on the display; returns its
                                         length; Backspace works; the '\n' is not kept       */
int read_int(void);                   /* read a line and convert it with atoi                 */

#endif
