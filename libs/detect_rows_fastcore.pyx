
def get_sq_dev_per_line(image, target_color):
    cdef:
        char *s
        int xbyte, y, xsize, ysize, xsize3
        double sq_dev
        unsigned char point
        unsigned char target_color_fast
    istr = image.tostring()
    s = istr
    xsize = image.size[0]
    ysize = image.size[1]
    target_color_fast = target_color
    xsize3 = xsize * 3
    res = []
    for y in range(ysize):
        sq_dev = 0
        for xbyte in range(xsize3):
            point = s[y*xsize3+xbyte]
            sq_dev += (target_color_fast-point) * (target_color_fast-point)
        res.append(sq_dev/3)
    return res
