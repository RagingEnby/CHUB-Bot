from typing import Optional, Literal, Any
import aiohttp
import disnake
import aiofiles
import json
import asyncio

from modules import mojang
from modules import misc

import datatypes
import config

BUTTON_ID = 'TradeReport'


PENDING_REPORTS: dict[str, datatypes.TradeReport] = {
    id_: datatypes.TradeReport.from_dict(trade)
    for id_, trade in json.load(open(config.TRADE_REPORT_FILE_PATH, 'r')).items()
}
INACTIVE_COMPONENTS: list[disnake.ui.Button] = [
    disnake.ui.Button(
        label="Accept",
        style=disnake.ButtonStyle.green,
        disabled=True
    ),
    disnake.ui.Button(
        label="Deny",
        style=disnake.ButtonStyle.red,
        disabled=True
    )
]


async def save_pending_reports():
    async with aiofiles.open(config.TRADE_REPORT_FILE_PATH, 'w') as file:
        await file.write(json.dumps({k: v.to_dict() for k, v in PENDING_REPORTS.items()}))


async def log_trade_report(report: datatypes.TradeReport):
    PENDING_REPORTS[report.id] = report
    await save_pending_reports()


async def on_button_click(inter: disnake.MessageInteraction, button_data: str):
    # im FULLY aware this is a bad and long function. i just cba to make it better
    # if it works it works :shrug:
    button_data: dict[str, Any] = json.loads(button_data)
    trade_report: Optional[datatypes.TradeReport] = PENDING_REPORTS.pop(button_data['id'], None)
    if trade_report is None:
        return await inter.send(embed=misc.make_error(
            "Invalid Trade",
            f"No trade with the ID `{disnake.utils.escape_markdown(button_data['id'])}`. This is likely because the trade has already been accepted or denied"
        ))
    author = inter.bot.get_user(trade_report.author) if trade_report.author else None
    
    if button_data['action'] != 'accept':
        return await inter.send(embed=misc.make_error(
            "Not Implimented",
            "This action is not yet implimented. This is a dev feature and is coming soon"
        ))
    await inter.response.send_modal(
        title="Send Trade Report",
        custom_id="send_trade_report",
        components=[
            disnake.ui.TextInput(
                label="Date",
                custom_id="date",
                style=disnake.TextInputStyle.short,
                min_length=6, max_length=10,
                placeholder=trade_report.date
            ),
            disnake.ui.TextInput(
                label="Item",
                custom_id="item",
                style=disnake.TextInputStyle.short,
                placeholder=trade_report.item
            ),
            disnake.ui.TextInput(
                label="Price",
                custom_id="price",
                style=disnake.TextInputStyle.short,
                placeholder=trade_report.price
            ),
            disnake.ui.TextInput(
                label="Overpay/Underpay",
                custom_id="overpay_underpay",
                style=disnake.TextInputStyle.short,
                min_length=3, max_length=5,
                placeholder="ENTER: 'over', 'under', or 'N/A'",
            )
        ]
    )
    try:
        modal_inter: disnake.ModalInteraction = await inter.bot.wait_for(
            "modal_submit",
            check=lambda i: i.custom_id == "send_trade_report" and i.author.id == inter.author.id,
            timeout=300
        )
        if not modal_inter.user.get_role(config.RECENT_SALES_JURY_ROLE):
            return await modal_inter.send(embed=misc.make_error(
                "No Permissions",
                f"You must have the <@&{config.RECENT_SALES_JURY_ROLE}> role to send trade reports"
            ))

        overpay_underpay = modal_inter.text_values["overpay_underpay"] if modal_inter.text_values["overpay_underpay"] != 'N/A' else None
        
        if overpay_underpay not in ['over', 'under', None]:
            return await modal_inter.send(embed=misc.make_error(
                "Invalid Overpay/Underpay value",
                f"You entered `{disnake.utils.escape_markdown(overpay_underpay)}`"
                " but it must be equal to `over`, `under`, or `N/A`"
            ))

        censor = '||' if overpay_underpay else ''
        content = censor + '\n'.join([
            "# " + overpay_underpay.upper() if overpay_underpay else '',
            f"**Buyer:** `{trade_report.buyer.name}`",
            f"**Seller:** `{trade_report.seller.name}`",
            f"**Date:** `{modal_inter.text_values['date']}`",
            f"**Item:** `{modal_inter.text_values['item']}`",
            f"**Price:** `{modal_inter.text_values['price']}`",
        ]) + censor
        # add an empty embed with the image so i dont have to bother with downloading the image
        embed = disnake.Embed()
        embed.set_image(url=self.trade.image.url)
        channel = inter.bot.get_channel(config.TRADE_REPORT_CHANNEL)
        await channel.send(content, embed=embed)
        await inter.message.edit(
            embed=trade_report.to_embed(status='accepted'),
            components=INACTIVE_COMPONENTS
        )

    except asyncio.TimeoutError:
        await inter.author.send('Your trade report window has timed out and is no longer valid.')


async def send_log_msg(inter: disnake.AppCmdInter, report: datatypes.TradeReport):
    channel = inter.bot.get_channel(config.TRADE_REPORT_VERIFICATION_CHANNEL)
    await channel.send()


async def report_trade_command(
    inter: disnake.AppCmdInter,
    seller_name: str,
    buyer_name: str,
    date: str,
    item: str,
    price: str,
    payment_type: datatypes.TradePaymentType,
    image: disnake.Attachment,
    notes: Optional[str]
):
    await inter.response.defer()
    if seller_name == buyer_name:
        return await inter.send(embed=misc.make_error(
            "Invalid Trade",
            "You cannot trade with yourself!"
        ))
        
    async with aiohttp.ClientSession() as session:
        seller = await mojang.get(seller_name, session=session)
        if seller is None:
            return await inter.send(embed=misc.make_error(
                "Invalid Seller",
                f"`{disnake.utils.escape_markdown(seller_name)}` is not a valid Minecraft IGN."
            ))
        buyer = await mojang.get(buyer_name, session=session)
        if buyer is None:
            return await inter.send(embed=misc.make_error(
                "Invalid Buyer",
                f"`{disnake.utils.escape_markdown(buyer_name)}` is not a valid Minecraft IGN."
            ))

        
        trade_report = datatypes.TradeReport(
            author=inter.user.id,
            seller=seller,
            buyer=buyer,
            date=date,
            item=item,
            price=price,
            payment_type=payment_type,
            image=datatypes.TradeReportAttachment.from_disnake_attachment(image),
            notes=notes
        )
        await log_trade_report(trade_report)
        
        channel = inter.bot.get_channel(config.TRADE_REPORT_VERIFICATION_CHANNEL)
        await channel.send(
            embed=trade_report.to_embed(),
            components=[
                disnake.ui.Button(
                    label="Accept",
                    style=disnake.ButtonStyle.green,
                    custom_id=f"{BUTTON_ID}|{json.dumps({'action': 'accept', 'id': trade_report.id})}"
                ),
                disnake.ui.Button(
                    label="Deny",
                    style=disnake.ButtonStyle.red,
                    custom_id=f"{BUTTON_ID}|{json.dumps({'action': 'deny', 'id': trade_report.id})}"
                )
            ]
        )
        