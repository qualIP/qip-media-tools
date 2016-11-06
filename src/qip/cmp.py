__all__ = [
        'strcmp',
        'genericcmp',
        'dictionarycmp',
        ]

def genericcmp(v1, v2):
    return (v1 > v2) - (v1 < v2)

def strcmp(str1, str2):
    return genericcmp(str(str1), str(str2))

def dictionarycmp(left, right):
    """This function compares two strings as if they were being used in an
    index or card catalog.  The case of alphabetic characters is ignored,
    except to break ties.  Thus "B" comes before "b" but after "a".  Also,
    integers embedded in the strings compare in numerical order.  In other
    words, "x10y" comes after "x9y", not before it as it would when using
    strcmp().
    Converted from Tcl's DictionaryCompare()
    """
    left = str(left)
    right = str(right)
    secondaryDiff = 0

    while True:
        if right[:1].isdigit() and left[:1].isdigit():
            # There are decimal numbers embedded in the two
            # strings.  Compare them as numbers, rather than
            # strings.  If one number has more leading zeros than
            # the other, the number with more leading zeros sorts
            # later, but only as a secondary choice.

            zeros = 0
            while right[:1] == '0' and right[1:2].isdigit():
                right = right[1:]
                zeros -= 1
            while left[:1] == '0' and left[1:2].isdigit():
                left = left[1:]
                zeros += 1
            if secondaryDiff == 0:
                secondaryDiff = zeros

            # The code below compares the numbers in the two
            # strings without ever converting them to integers.  It
            # does this by first comparing the lengths of the
            # numbers and then comparing the digit values.

            diff = 0
            while True:
                if diff == 0:
                    diff = (ord(left[0]) if left else 0) - \
                            (ord(right[0]) if right else 0)
                right = right[1:]
                left = left[1:]
                if not right[:1].isdigit():
                    if left[:1].isdigit():
                        return 1
                    else:
                        # The two numbers have the same length. See
                        # if their values are different.

                        if diff != 0:
                            return diff
                        break;
                elif not left[:1].isdigit():
                    return -1
            continue

        # If either string is at the terminating null, do a byte-wise
        # comparison and bail out immediately.
        if left and right:
            uniLeft = left[0]
            left = left[1:]
            uniRight = right[0]
            right = right[1:]

            # Convert both chars to lower for the comparison, because
            # dictionary sorts are case insensitve.  Covert to lower, not
            # upper, so chars between Z and a will sort before A (where most
            # other interesting punctuations occur)

            uniLeftLower = uniLeft.lower()
            uniRightLower = uniRight.lower()

        else:
            diff = (ord(left[0]) if left else 0) - \
                    (ord(right[0]) if right else 0)
            break

        diff = ord(uniLeftLower) - ord(uniRightLower)
        if diff:
            return diff
        elif secondaryDiff == 0:
            if uniLeft.isupper() and uniRight.islower():
                secondaryDiff = -1
            elif uniRight.isupper() and uniLeft.islower():
                secondaryDiff = 1

    if diff == 0:
        diff = secondaryDiff
    return diff

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
